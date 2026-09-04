"""Compatibility API consumed by the Basic Scan UI."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import PROJECT_ROOT, get_settings
from app.diagnosis.explainer import ollama_status
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import UiDiagnosis
from app.services import diagnosis_service, local_scan_service, scan_service

router = APIRouter()


class ScanRequest(BaseModel):
    snapshot: TelemetrySnapshot | None = None


def _validate_scan_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origin_list:
        raise HTTPException(status_code=403, detail="허용되지 않은 Origin의 로컬 스캔 요청입니다.")


def _latest_or_404() -> TelemetrySnapshot:
    snapshot = scan_service.latest_snapshot_any()
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="저장된 스냅샷이 없습니다. Local Agent에서 scan --upload를 먼저 실행하세요.",
        )
    return snapshot


@router.get("/health")
def ui_health() -> dict:
    settings = get_settings()
    latest = scan_service.latest_snapshot_any()
    return {
        "status": "ok",
        "agentVersion": latest.agent.version if latest else "not-connected",
        "host": "127.0.0.1",
        "backendVersion": settings.app_version,
        "gemma": ollama_status(),
    }


@router.get("/schema/diagnosis")
def diagnosis_schema() -> JSONResponse:
    path = PROJECT_ROOT / "schemas" / "diagnosis.schema.json"
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@router.get("/scans/latest", response_model=UiDiagnosis)
def latest_diagnosis() -> UiDiagnosis:
    return diagnosis_service.diagnose_for_ui(_latest_or_404())


@router.post("/scans/start", status_code=status.HTTP_202_ACCEPTED)
def start_local_scan(request: Request) -> dict:
    _validate_scan_origin(request)
    state, started = local_scan_service.start_scan()
    return {**state, "started": started}


@router.get("/scans/status")
def local_scan_status() -> dict:
    return local_scan_service.get_status()


@router.post("/scans", response_model=UiDiagnosis)
def run_basic_scan(request: ScanRequest) -> UiDiagnosis:
    snapshot = request.snapshot
    if snapshot is not None:
        scan_service.save_snapshot(snapshot)
    else:
        snapshot = _latest_or_404()
    return diagnosis_service.diagnose_for_ui(snapshot)
