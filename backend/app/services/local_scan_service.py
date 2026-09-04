"""Run the Windows Local Agent as a single background scan job."""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT, get_settings
from app.services import scan_service

LOGGER = logging.getLogger(__name__)
_LOCK = threading.Lock()
_ACTIVE_STATES = {"running"}
_STATE: dict[str, Any] = {
    "runId": None,
    "status": "idle",
    "phase": "idle",
    "progress": 0,
    "currentCollector": None,
    "message": "실행 중인 스캔이 없습니다.",
    "scanId": None,
    "startedAt": None,
    "finishedAt": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def _is_elevated() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_agent(status_file: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("로컬 관리자 스캔은 Windows에서만 실행할 수 있습니다.")

    agent_dir = PROJECT_ROOT / "agent"
    arguments = [
        "-m",
        "speccheck_agent",
        "scan",
        "--upload",
        "--quiet",
        "--status-file",
        str(status_file),
    ]
    environment = os.environ.copy()
    backend_url = get_settings().local_agent_backend_url.rstrip("/")
    environment["SPECCHECK_BACKEND_URL"] = backend_url

    if _is_elevated():
        process = subprocess.run(
            [sys.executable, *arguments],
            cwd=agent_dir,
            env=environment,
            capture_output=True,
            timeout=300,
            check=False,
        )
        if process.returncode != 0:
            detail = process.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "Agent 실행에 실패했습니다.")
        return

    argument_list = ",".join("'{0}'".format(_powershell_quote(value)) for value in arguments)
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$env:SPECCHECK_BACKEND_URL = '{backend_url}'; "
        "$process = Start-Process -FilePath '{python}' -Verb RunAs -WindowStyle Hidden "
        "-WorkingDirectory '{agent}' -ArgumentList @({arguments}) -Wait -PassThru; "
        "exit $process.ExitCode"
    ).format(
        python=_powershell_quote(sys.executable),
        agent=_powershell_quote(str(agent_dir)),
        arguments=argument_list,
        backend_url=_powershell_quote(backend_url),
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    process = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        timeout=300,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        LOGGER.warning("Elevated Agent launch failed: %s", detail or process.returncode)
        raise RuntimeError(
            "Windows가 관리자 Agent를 시작하지 못했습니다. Backend를 관리자 권한으로 실행한 뒤 다시 시도하세요."
        )


def _set_state(**values: Any) -> None:
    with _LOCK:
        _STATE.update(values)


def _worker(status_file: Path, previous_scan_id: str | None) -> None:
    try:
        _run_agent(status_file)

        latest = scan_service.latest_snapshot_any()
        if latest is None or latest.snapshot_id == previous_scan_id:
            raise RuntimeError("Agent는 종료됐지만 새 Snapshot이 업로드되지 않았습니다.")

        _set_state(
            status="completed",
            phase="completed",
            progress=100,
            currentCollector=None,
            message="수집과 진단 데이터 업로드가 완료됐습니다.",
            scanId=latest.snapshot_id,
            finishedAt=_now(),
        )
    except subprocess.TimeoutExpired:
        _set_state(
            status="failed",
            phase="failed",
            message="스캔 제한 시간 5분을 초과했습니다.",
            finishedAt=_now(),
        )
    except Exception as exc:
        _set_state(
            status="failed",
            phase="failed",
            message=str(exc),
            finishedAt=_now(),
        )


def start_scan() -> tuple[dict[str, Any], bool]:
    """Start one scan, returning the current state and whether it was newly started."""
    with _LOCK:
        if _STATE["status"] in _ACTIVE_STATES:
            return dict(_STATE), False

        run_id = str(uuid.uuid4())
        previous = scan_service.latest_snapshot_any()
        status_dir = PROJECT_ROOT / "backend" / "data" / "scan-runs"
        status_dir.mkdir(parents=True, exist_ok=True)
        status_file = status_dir / "{0}.json".format(run_id)
        _STATE.update(
            runId=run_id,
            status="running",
            phase="permission",
            progress=0,
            currentCollector=None,
            message="Windows 관리자 권한 승인 후 수집을 시작합니다.",
            scanId=None,
            startedAt=_now(),
            finishedAt=None,
            _status_file=str(status_file),
        )

    thread = threading.Thread(
        target=_worker,
        args=(status_file, previous.snapshot_id if previous else None),
        daemon=True,
        name="speccheck-local-scan",
    )
    thread.start()
    return get_status(), True


def get_status() -> dict[str, Any]:
    with _LOCK:
        state = dict(_STATE)

    status_file = state.pop("_status_file", None)
    if state["status"] == "running" and status_file:
        try:
            progress = json.loads(Path(status_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            progress = None
        if progress:
            state.update(
                phase=progress.get("phase", state["phase"]),
                progress=progress.get("progress", state["progress"]),
                currentCollector=progress.get("collector"),
                message=progress.get("message", state["message"]),
            )
    return state


def _reset_for_tests() -> None:
    _set_state(
        runId=None,
        status="idle",
        phase="idle",
        progress=0,
        currentCollector=None,
        message="실행 중인 스캔이 없습니다.",
        scanId=None,
        startedAt=None,
        finishedAt=None,
        _status_file=None,
    )
