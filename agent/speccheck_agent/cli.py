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
from typing import Any

from . import __version__
from .collectors import iter_collectors, registry
from .config import AgentConfig
from .pipeline import SnapshotStore, to_spec_profile
from .snapshot import SCHEMA_VERSION, build_snapshot, summarize
from .transport import UploadError, upload_snapshot


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# --- 명령 ----------------------------------------------------------------


def cmd_scan(args: argparse.Namespace, config: AgentConfig) -> int:
    names = [name.strip() for name in args.collectors.split(",")] if args.collectors else None

    results = []
    for collector in iter_collectors(names):
        if not args.quiet:
            print("  - {0} ...".format(collector.name), end="", flush=True)
        result = collector.run()
        if not args.quiet:
            print(" {0}".format(result.status))
        results.append(result)

    snapshot = build_snapshot(
        results,
        scan_mode=args.mode,
        device_id=config.device_id,
        notes=args.note,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(_dump(snapshot))
        print("저장: {0}".format(args.out))

    if not args.no_save:
        config.ensure_dirs()
        with SnapshotStore(config.db_path) as store:
            store.save(snapshot)
        print("로컬 DB: {0}".format(config.db_path))

    if args.upload:
        try:
            response = upload_snapshot(snapshot, config.backend_url, config.upload_timeout)
        except UploadError as exc:
            print("업로드 실패: {0}".format(exc), file=sys.stderr)
            return 1
        print("업로드 완료: {0}".format(response.get("snapshot_id", "?")))
        if not args.no_save:
            with SnapshotStore(config.db_path) as store:
                store.mark_uploaded(snapshot["snapshot_id"])

    if args.json:
        print(_dump(snapshot))
    else:
        print(summarize(snapshot))
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
    checks: list[tuple[str, bool, str]] = []

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

    config.ensure_dirs()
    checks.append(("Agent Home", config.home.exists(), str(config.home)))
    checks.append(("Backend URL", True, config.backend_url))
    checks.append(("Schema", True, SCHEMA_VERSION))

    for label, ok, detail in checks:
        print("{0} {1:<16}{2}".format("[OK]  " if ok else "[FAIL]", label, detail))

    return 0 if all(ok for _, ok, _ in checks) else 1


# --- 파서 ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speccheck-agent",
        description="SpecCheck Local Agent - PC telemetry 수집기",
    )
    parser.add_argument("--version", action="version", version="speccheck-agent " + __version__)
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AgentConfig()
    return int(args.func(args, config))
