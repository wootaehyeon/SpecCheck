"""Agent CLI.

    python -m speccheck_agent scan            # 스캔 실행 후 로컬 저장
    python -m speccheck_agent scan --upload   # 스캔 후 Backend 전송
    python -m speccheck_agent collectors      # 등록된 collector 목록
    python -m speccheck_agent list            # 최근 스냅샷
    python -m speccheck_agent show <id>       # 스냅샷 원문 출력
    python -m speccheck_agent profile         # 최신 스냅샷의 부품 사양 프로필
    python -m speccheck_agent doctor          # 실행 환경 점검
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import logging
import sqlite3
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import __version__
from .collectors import iter_collectors, registry
from .config import AgentConfig
from .pipeline import SnapshotStore, to_spec_profile
from .snapshot import SCHEMA_VERSION, build_snapshot, summarize
from .transport import UploadError, upload_snapshot
from .analysis import analyze_snapshot


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# --- 명령 ----------------------------------------------------------------


def cmd_scan(args: argparse.Namespace, config: AgentConfig) -> int:
    names = [name.strip() for name in args.collectors.split(",")] if args.collectors else None

    selected = list(iter_collectors(names))
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda collector: collector.run(), selected))
    for result in results:
        logging.getLogger('speccheck_agent').info('%s status=%s duration_ms=%s', result.name, result.status, result.duration_ms)
        if not args.quiet and not args.json:
            print('  - {0}: {1}'.format(result.name, result.status))

    snapshot = build_snapshot(
        results,
        scan_mode=args.mode,
        device_id=config.device_id,
        notes=args.note,
    )
    history = []
    if config.db_path.exists():
        with SnapshotStore(config.db_path) as store:
            history = store.history(snapshot['device_id'], snapshot['collected_at'])
    analyze_snapshot(snapshot, history)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(_dump(snapshot))
        if not args.json and not args.quiet:
            print("저장: {0}".format(args.out))

    if not args.no_save:
        config.ensure_dirs()
        with SnapshotStore(config.db_path) as store:
            store.save(snapshot)
        if not args.json and not args.quiet:
            print("로컬 DB: {0}".format(config.db_path))

    if args.upload:
        try:
            response = upload_snapshot(snapshot, config.backend_url, config.upload_timeout)
        except UploadError as exc:
            print("업로드 실패: {0}".format(exc), file=sys.stderr)
            return 1
        if not args.json and not args.quiet:
            print("업로드 완료: {0}".format(response.get("snapshot_id", "?")))
        if not args.no_save:
            with SnapshotStore(config.db_path) as store:
                store.mark_uploaded(snapshot["snapshot_id"])

    if args.json:
        print(_dump(snapshot))
    else:
        print(summarize(snapshot))
    return 0


def cmd_analyze(args, config):
    with SnapshotStore(config.db_path) as store:
        snapshot = store.get(args.snapshot_id) if args.snapshot_id else store.latest()
        if snapshot is None:
            print('No saved snapshot found.', file=sys.stderr)
            return 1
        history = store.history(snapshot['device_id'], snapshot['collected_at'])
    analyze_snapshot(snapshot, history)
    print(_dump({k: snapshot['sections'][k] for k in ('correlation', 'anomaly', 'trajectory')}))
    return 0


def cmd_prune(args, config):
    with SnapshotStore(config.db_path) as store:
        count = store.prune(args.keep)
    print('Removed {0} snapshots.'.format(count))
    return 0


def cmd_collectors(args: argparse.Namespace, config: AgentConfig) -> int:
    print("{0:<16}{1:<8}{2:<10}{3}".format("NAME", "M", "STATE", "DESCRIPTION"))
    for name, cls in registry().items():
        state = "ready" if cls.implemented else "planned"
        print("{0:<16}{1:<8}{2:<10}{3}".format(name, cls.milestone, state, cls.description))
    return 0


def cmd_list(args: argparse.Namespace, config: AgentConfig) -> int:
    with SnapshotStore(config.db_path) as store:
        rows = store.list_recent(args.limit)
    if not rows:
        print("저장된 스냅샷이 없습니다. 먼저 'scan' 을 실행하세요.")
        return 0
    for row in rows:
        print(
            "{0}  {1}  {2:<10}{3}".format(
                row["snapshot_id"][:8],
                row["collected_at"],
                row["scan_mode"],
                "uploaded" if row["uploaded_at"] else "local",
            )
        )
    return 0


def cmd_show(args: argparse.Namespace, config: AgentConfig) -> int:
    with SnapshotStore(config.db_path) as store:
        snapshot = store.get(args.snapshot_id) if args.snapshot_id else store.latest()
    if snapshot is None:
        print("스냅샷을 찾을 수 없습니다.", file=sys.stderr)
        return 1
    print(_dump(snapshot))
    return 0


def cmd_profile(args: argparse.Namespace, config: AgentConfig) -> int:
    with SnapshotStore(config.db_path) as store:
        snapshot = store.get(args.snapshot_id) if args.snapshot_id else store.latest()
    if snapshot is None:
        print("스냅샷을 찾을 수 없습니다. 먼저 'scan' 을 실행하세요.", file=sys.stderr)
        return 1
    print(_dump(to_spec_profile(snapshot)))
    return 0


def cmd_doctor(args: argparse.Namespace, config: AgentConfig) -> int:
    checks: list[tuple[str, bool | None, str]] = []

    is_windows = platform.system() == "Windows"
    checks.append(("OS", is_windows, platform.platform()))
    checks.append(("Python", sys.version_info >= (3, 10), sys.version.split()[0]))

    powershell_ok = False
    detail = "확인 불가 (Windows 아님)"
    if is_windows:
        from .win import cim

        try:
            cim.run_powershell("$PSVersionTable.PSVersion.ToString()", timeout=15)
            powershell_ok = True
            detail = "Get-CimInstance 사용 가능"
        except cim.CimError as exc:
            detail = str(exc)
    checks.append(("PowerShell/CIM", powershell_ok, detail))
    if powershell_ok:
        from .win.events import probe_sysmon
        sysmon = probe_sysmon()
        # Optional checks inform the user without making doctor fail.
        checks.append(('Sysmon (optional)', True if sysmon['status'] == 'ok' else None,
                       sysmon['status'] + ': ' + sysmon['reason']))
        import ctypes
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        checks.append(('Admin (optional)', True if admin else None, 'yes' if admin else 'no; protected counters may be unavailable'))
        try:
            policy = cim.run_powershell('Get-ExecutionPolicy', timeout=5).strip()
            checks.append(('Execution policy', True, policy))
        except cim.CimError:
            checks.append(('Execution policy', None, 'unavailable; review PowerShell policy'))

    config.ensure_dirs()
    checks.append(("Agent Home", config.home.exists(), str(config.home)))
    checks.append(("Backend URL", True, config.backend_url))
    checks.append(("Schema", True, SCHEMA_VERSION))

    for label, ok, detail in checks:
        badge = '[WARN]' if ok is None else '[OK]' if ok else '[FAIL]'
        print('{0:<6} {1:<22} {2}'.format(badge, label, detail))

    return 0 if all(ok is not False for _, ok, _ in checks) else 1


# --- 파서 ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speccheck-agent",
        description="SpecCheck Local Agent - PC telemetry 수집기",
    )
    parser.add_argument("--version", action="version", version="speccheck-agent " + __version__)
    parser.add_argument('--verbose', action='store_true', help='diagnostic status logging to stderr')
    parser.add_argument('--log-file', action='store_true', help='enable rotating local status log')
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="telemetry 수집")
    scan.add_argument("--mode", choices=["actual", "estimated"], default="actual")
    scan.add_argument("--collectors", help="쉼표로 구분한 collector 이름 (기본: 전체)")
    scan.add_argument("--out", help="스냅샷 JSON 파일 경로")
    scan.add_argument("--json", action="store_true", help="스냅샷 전체를 표준 출력으로")
    scan.add_argument("--no-save", action="store_true", help="로컬 DB에 저장하지 않음")
    scan.add_argument("--upload", action="store_true", help="Backend로 전송")
    scan.add_argument("--note", help="스냅샷에 남길 메모 (예: 'RAM 교체 전')")
    scan.add_argument("--quiet", action="store_true")
    scan.set_defaults(func=cmd_scan)

    collectors = subparsers.add_parser("collectors", help="등록된 collector 목록")
    collectors.set_defaults(func=cmd_collectors)

    listing = subparsers.add_parser("list", help="최근 스냅샷 목록")
    listing.add_argument("--limit", type=int, default=20)
    listing.set_defaults(func=cmd_list)

    show = subparsers.add_parser("show", help="스냅샷 원문 출력")
    show.add_argument("snapshot_id", nargs="?", help="생략 시 최신 스냅샷")
    show.set_defaults(func=cmd_show)

    profile = subparsers.add_parser("profile", help="부품 사양 프로필 추출")
    profile.add_argument("snapshot_id", nargs="?")
    profile.set_defaults(func=cmd_profile)

    doctor = subparsers.add_parser("doctor", help="실행 환경 점검")
    doctor.set_defaults(func=cmd_doctor)

    analysis = subparsers.add_parser('analyze', help='local correlation / anomaly / trajectory')
    analysis.add_argument('snapshot_id', nargs='?')
    analysis.set_defaults(func=cmd_analyze)
    prune = subparsers.add_parser('prune', help='retain newest snapshots per device')
    prune.add_argument('--keep', type=int, default=200)
    prune.set_defaults(func=cmd_prune)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AgentConfig()
    logger = logging.getLogger('speccheck_agent')
    handlers = []
    try:
        if args.verbose:
            handlers.append(logging.StreamHandler())
        if args.log_file:
            config.ensure_dirs()
            handlers.append(RotatingFileHandler(config.home / 'agent.log', maxBytes=1048576, backupCount=2, encoding='utf-8'))
        logger.setLevel(logging.INFO)
        for handler in handlers:
            logger.addHandler(handler)
        return int(args.func(args, config))
    except (KeyError, ValueError, OSError, sqlite3.Error) as exc:
        print('Agent command failed ({0}); check arguments and local storage permissions.'.format(type(exc).__name__), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
