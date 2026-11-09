"""공개 웹용 인증 모니터링 API. 기존 인증 없는 scan API와 분리한다."""
from __future__ import annotations

import io
import json
import threading
import time
import zipfile
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse, RedirectResponse
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, StrictBool, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import PROJECT_ROOT, get_settings
from app.schemas.telemetry import TelemetrySnapshot, SUPPORTED_SCHEMA_MAJOR
from app.services import monitoring_service as service

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
MAX_BODY = 1024 * 1024
_pair_attempts = defaultdict(deque)
_pair_lock = threading.Lock()
_redeem_attempts = defaultdict(deque)
_redeem_lock = threading.Lock()


def require_ready():
    if not service.configured():
        raise HTTPException(503, "모니터링 DB가 아직 연결되지 않았습니다. 서버의 MONITORING_DATABASE_URL을 설정하세요.")


def _auth(credentials, scope):
    require_ready()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "이 PC의 연결키가 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    device = service.authenticate(credentials.credentials, scope)
    if device is None:
        raise HTTPException(401, "연결키가 만료되었거나 권한이 맞지 않습니다.", headers={"WWW-Authenticate": "Bearer"})
    return device


def reader(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    return _auth(credentials, "read")


def writer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    return _auth(credentials, "write")


class PairRequest(BaseModel):
    name: str = Field(default="내 PC", min_length=1, max_length=64)
    accepted: bool
    security_accepted: bool = False


class SecurityConsentRequest(BaseModel):
    accepted: StrictBool


class RedeemRequest(BaseModel):
    code: str = Field(min_length=8, max_length=16, pattern=r"^[A-Za-z2-9 -]+$")
    accepted: StrictBool


def agent_download_ready():
    cfg = get_settings()
    return cfg.monitoring_agent_exe.is_file() or valid_download_url(cfg.monitoring_agent_download_url)


def valid_download_url(url: str) -> bool:
    parsed = urlsplit(url)
    return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password)


@router.get("/status")
def status():
    cfg = get_settings()
    return {"enabled": service.configured(), "persistent": cfg.monitoring_database_url.startswith(("postgres://", "postgresql")),
            "retention_days": 7, "connection_days": 90, "agent_download_available": agent_download_ready()}


@router.post("/pair", dependencies=[Depends(require_ready)], status_code=201)
def pair(payload: PairRequest, request: Request):
    if not payload.accepted:
        raise HTTPException(422, "수집 항목과 서버 전송에 동의해야 합니다.")
    now = time.monotonic()
    ip = request.client.host if request.client else "unknown"
    with _pair_lock:
        if len(_pair_attempts) > 4096:
            for key in list(_pair_attempts):
                if not _pair_attempts[key] or _pair_attempts[key][-1] < now - 3600:
                    del _pair_attempts[key]
        attempts = _pair_attempts[ip]
        while attempts and attempts[0] < now - 3600:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "새 PC 연결은 한 시간에 10회까지 가능합니다.")
        attempts.append(now)
    return service.pair(payload.name.strip() or "내 PC", payload.security_accepted)


@router.post("/agent-config")
def agent_config(device=Depends(reader)):
    return {"version": 1, "device_id": device["id"], "name": device["name"],
            "writer_token": service.issue_writer(device), "security_consent": device["security_allowed"],
            "consent_version": "monitor-v1", "consent_at": device["consent_at"], "interval": 30}


@router.post("/pairing-code")
def pairing_code(device=Depends(reader)):
    return service.issue_pairing_code(device)


@router.post("/redeem", dependencies=[Depends(require_ready)])
def redeem(payload: RedeemRequest, request: Request):
    if not payload.accepted:
        raise HTTPException(422, "프로그램에서 수집과 서버 전송에 동의하고 시작해주세요.")
    now = time.monotonic()
    ip = request.client.host if request.client else "unknown"
    with _redeem_lock:
        for key in list(_redeem_attempts):
            if not _redeem_attempts[key] or _redeem_attempts[key][-1] <= now - 600:
                del _redeem_attempts[key]
        attempts = _redeem_attempts[ip]
        while attempts and attempts[0] <= now - 600:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "연결 시도가 많습니다. 10분 후 다시 시도해주세요.")
        attempts.append(now)
    config = service.redeem_pairing_code(payload.code)
    if config is None:
        raise HTTPException(400, "연결 코드가 올바르지 않거나 만료되었습니다. 웹에서 새 코드를 발급해주세요.")
    return config


@router.get("/agent.exe")
def download_agent_exe():
    cfg = get_settings()
    if cfg.monitoring_agent_exe.is_file():
        return FileResponse(cfg.monitoring_agent_exe, media_type="application/vnd.microsoft.portable-executable",
                            filename="SpecCheck-Agent.exe")
    if valid_download_url(cfg.monitoring_agent_download_url):
        return RedirectResponse(cfg.monitoring_agent_download_url, status_code=307)
    raise HTTPException(503, "Windows 프로그램을 준비 중입니다. 잠시 후 다시 다운로드해주세요.")


@router.put("/security-consent")
def security_consent(payload: SecurityConsentRequest, device=Depends(reader)):
    return service.set_security_consent(device, payload.accepted)


@router.post("/snapshots", status_code=201)
async def upload(request: Request, device=Depends(writer)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(413, "스냅샷은 1 MiB 이하로 보내주세요.")
    try:
        payload = json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        snapshot = TelemetrySnapshot.model_validate(payload)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, "스냅샷 형식이 올바르지 않습니다.") from None
    if snapshot.device_id != device["id"]:
        raise HTTPException(403, "이 연결키에 등록된 PC만 업로드할 수 있습니다.")
    if snapshot.schema_major != SUPPORTED_SCHEMA_MAJOR or snapshot.scan_mode != "actual":
        raise HTTPException(422, "실측 Agent 스냅샷이 필요합니다.")
    if len(snapshot.snapshot_id) > 64 or set(snapshot.sections) - {"hardware", "performance", "security"}:
        raise HTTPException(422, "모니터링에서 지원하지 않는 수집 항목입니다.")
    if "security" in snapshot.sections and not device["security_allowed"]:
        raise HTTPException(403, "프로세스 이력 전송은 별도 동의가 필요합니다.")
    received_at = await run_in_threadpool(service.save, device, snapshot)
    return {"snapshot_id": snapshot.snapshot_id, "received_at": received_at}


@router.get("/latest")
def latest(device=Depends(reader)):
    return service.latest(device)


@router.get("/assistance")
def assistance(snapshot_id: str | None = Query(default=None, min_length=1, max_length=64),
               device=Depends(writer)):
    result = service.assistance(device, snapshot_id)
    if result is None:
        raise HTTPException(404, "이 PC의 진단 자료가 없습니다. Agent에서 먼저 수집·전송해주세요.")
    return result


@router.get("/history")
def history(limit: int = Query(default=240, ge=1, le=1440), device=Depends(reader)):
    return service.history(device, limit)


@router.get("/process-events")
def events(limit: int = Query(default=200, ge=1, le=1000), device=Depends(reader)):
    return service.process_events(device, limit)


@router.delete("/connection", status_code=204)
def disconnect(device=Depends(reader)):
    service.disconnect(device)
    return Response(status_code=204)


@router.get("/agent.zip")
def download_agent():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (PROJECT_ROOT / "agent" / "speccheck_agent").rglob("*.py"):
            archive.write(path, "SpecCheck-Agent/" + path.relative_to(PROJECT_ROOT / "agent").as_posix())
        launcher = PROJECT_ROOT / "agent" / "Start-SpecCheck.cmd"
        archive.write(launcher, "SpecCheck-Agent/Start-SpecCheck.cmd")
    return Response(output.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="SpecCheck-Agent.zip"'})
