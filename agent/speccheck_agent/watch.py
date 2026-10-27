"""웹에서 발급한 기기 전송키로 실측값을 보내는 명시적 동의 기반 모니터."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from .collectors.hardware import HardwareCollector
from .collectors.performance import PerformanceCollector
from .collectors.security import SecurityCollector
from .config import AgentConfig
from .pipeline import SnapshotStore
from .snapshot import build_snapshot
from .win.cim import is_elevated, is_windows


def load_connection(path: str) -> dict:
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    parsed = urlsplit(config.get("backend_url", ""))
    loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if (parsed.scheme != "https" and not (loopback and parsed.scheme == "http")) or not parsed.hostname:
        raise ValueError("서버 주소는 HTTPS여야 합니다.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("서버 주소에는 경로, 사용자 정보, 쿼리를 넣을 수 없습니다.")
    if config.get("version") != 1 or config.get("consent_version") != "monitor-v1":
        raise ValueError("웹에서 새 연결 설정을 내려받아주세요.")
    UUID(config["device_id"])
    token = config.get("writer_token", "")
    if not isinstance(token, str) or not token.startswith("sc_write_") or len(token) > 256:
        raise ValueError("PC 전송키가 올바르지 않습니다.")
    interval = config.get("interval", 30)
    if type(interval) is not int or not 10 <= interval <= 3600:
        raise ValueError("수집 간격은 10~3600초여야 합니다.")
    if type(config.get("security_consent", False)) is not bool:
        raise ValueError("프로세스 이력 동의 값이 올바르지 않습니다.")
    config["backend_url"] = config["backend_url"].rstrip("/")
    return config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 전송키가 다른 주소로 전달되지 않도록 리다이렉트를 허용하지 않는다.
        return None


class WatchUploadError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def upload(snapshot: dict, connection: dict, timeout: float = 15.0) -> None:
    request = urllib.request.Request(connection["backend_url"] + "/api/monitor/snapshots",
        data=json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + connection["writer_token"]},
        method="POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 201:
                raise WatchUploadError("모니터링 서버가 전송을 수락하지 않았습니다.", response.status)
    except urllib.error.HTTPError as exc:
        raise WatchUploadError("서버 응답 HTTP {0}. 연결 설정과 DB 상태를 확인해주세요.".format(exc.code), exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise WatchUploadError("서버에 연결하지 못했습니다. 로컬에 보관하고 다음 회차에 재시도합니다.") from None


def _public_snapshot(snapshot: dict) -> dict:
    # 오류 메시지에 로컬 경로가 섞일 수 있으므로 서버에는 수집 상태만 보낸다.
    snapshot = json.loads(json.dumps(snapshot))
    for section in snapshot["sections"].values():
        if section.get("error"):
            section["error"] = "수집하지 못했습니다. 로컬 Agent 로그를 확인해주세요."
        section.get("data", {}).pop("collect_errors", None)
    snapshot["notes"] = None
    return snapshot


def pending(store: SnapshotStore, device_id: str, security_consent: bool):
    rows = store.connect().execute(
        "SELECT payload FROM snapshots WHERE device_id = ? AND uploaded_at IS NULL "
        "AND (? OR NOT EXISTS (SELECT 1 FROM collector_runs WHERE collector_runs.snapshot_id = snapshots.snapshot_id AND name = 'security')) "
        "ORDER BY collected_at LIMIT 10",
        (device_id, security_consent),
    ).fetchall()
    for row in rows:
        snapshot = json.loads(row[0])
        if "security" in snapshot.get("sections", {}) and not security_consent:
            continue
        yield snapshot


def cmd_watch(args: argparse.Namespace, config: AgentConfig) -> int:
    if not args.consent:
        print("수집과 서버 전송 동의가 필요합니다. --consent를 지정한 경우에만 시작합니다.")
        return 2
    try:
        connection = load_connection(args.config)
    except (OSError, ValueError, KeyError, TypeError):
        print("연결 설정 파일을 읽을 수 없습니다. 웹에서 speccheck-monitor.json을 다시 내려받아주세요.")
        return 2
    if not is_windows():
        print("PC 모니터링 Agent는 Windows에서 실행해주세요.")
        return 2
    security_enabled = connection.get("security_consent", False) and args.security_consent
    if security_enabled and not is_elevated():
        print("프로세스 이력을 선택했습니다. Start-SpecCheck.cmd를 우클릭하여 관리자 권한으로 실행해주세요.")
        return 2
    local_dir = config.home / "monitor" / connection["device_id"]
    local_dir.mkdir(parents=True, exist_ok=True)
    security = SecurityCollector(consent=True, since=datetime.now(timezone.utc)) if security_enabled else None
    hardware = None
    last_inventory = 0.0
    print("실측 PC 모니터링을 시작합니다. 서버: " + connection["backend_url"])
    print("CPU·메모리·디스크 부하, 하드웨어 사양과 상위 점유 프로세스 이름을 전송합니다.")
    print("프로세스 이력: " + ("Sysmon 수집 사용" if security_enabled else "수집하지 않음"))
    print("Ctrl+C로 중단합니다. 원본은 로컬 DB에 남고 서버 이력은 7일 보관합니다.")
    try:
        with SnapshotStore(local_dir / "agent.db") as store:
            while True:
                started = time.monotonic()
                if hardware is None or started - last_inventory >= 300:
                    hardware = HardwareCollector().run()
                    last_inventory = started
                results = [hardware, PerformanceCollector().run()]
                if security:
                    result = security.run()
                    results.append(result)
                    if security.failure_code in ("access_denied", "log_unavailable", "log_disabled"):
                        print("Sysmon 수집 실패: " + (result.error or "권한/설치 상태를 확인해주세요."))
                        return 2
                snapshot = build_snapshot(results, device_id=connection["device_id"])
                store.save(snapshot)
                if security:
                    security.acknowledge(results[-1].data)
                for saved in pending(store, connection["device_id"], security_enabled):
                    try:
                        upload(_public_snapshot(saved), connection)
                    except WatchUploadError as exc:
                        print(str(exc))
                        if exc.status in (401, 403):
                            print("웹에서 연결 설정을 다시 내려받거나 수집 동의를 확인해주세요.")
                            return 1
                        break
                    store.mark_uploaded(saved["snapshot_id"])
                print(snapshot["collected_at"] + " 수집 완료")
                if args.once:
                    return 0
                time.sleep(max(1.0, connection.get("interval", 30) - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("모니터링을 중단했습니다. 웹의 연결 해제로 서버 이력과 키를 삭제할 수 있습니다.")
    return 0
