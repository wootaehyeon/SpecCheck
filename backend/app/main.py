"""FastAPI 진입점."""

import hashlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import PROJECT_ROOT, get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AI 기반 PC Lifecycle Platform - 진단 / 견적 / 가격 분석",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"message": "SpecCheck AI Backend is running 🚀", "version": settings.app_version}


@app.get("/health")
def health():
    """배포 헬스체크 및 Agent의 backend 연결 확인용."""
    project_id = hashlib.sha256(str(PROJECT_ROOT.resolve()).replace("\\", "/").lower().encode()).hexdigest()[:16]
    return {
        "status": "ok", "app": settings.app_name, "version": settings.app_version,
        "projectId": project_id, "corsOrigins": settings.cors_origin_list,
        "localAgentBackendUrl": settings.local_agent_backend_url,
    }
