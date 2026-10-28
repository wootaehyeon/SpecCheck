"""FastAPI 진입점."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import create_router
from app.core.config import PROJECT_ROOT, get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="AI 기반 PC Lifecycle Platform - 진단 / 견적 / 가격 분석",
        version=settings.app_version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials="*" not in settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(
        create_router(telemetry_enabled=settings.telemetry_api_enabled), prefix="/api"
    )

    @app.middleware("http")
    async def private_monitoring_responses(request: Request, call_next):
        private = request.url.path.startswith("/api/monitor/")
        try:
            response = await call_next(request)
        except (SQLAlchemyError, ValueError):
            if not private:
                raise
            response = JSONResponse(status_code=503, content={"detail": "모니터링 DB 연결을 확인해주세요."})
        if private:
            response.headers["Cache-Control"] = "no-store"
        if request.url.path in {"/monitor.html", "/purchase.html"}:
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' https://cdn.jsdelivr.net; "
                "font-src 'self' https://cdn.jsdelivr.net; connect-src 'self'; img-src 'self' data:; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        return response

    @app.get("/health")
    def health():
        """배포 헬스체크 및 Agent의 backend 연결 확인용."""
        return {"status": "ok", "app": settings.app_name, "version": settings.app_version}

    if settings.serve_frontend:
        # API와 health를 먼저 등록하고 웹 자산 폴더만 공개한다.
        app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend" / "web", html=True), name="web")
    else:
        @app.get("/")
        def root():
            return {"message": "SpecCheck AI Backend is running 🚀", "version": settings.app_version}

    return app


app = create_app()
