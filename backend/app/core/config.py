"""애플리케이션 설정.

환경변수 또는 ``backend/.env`` 에서 읽는다. 샘플은 ``backend/.env.example``.
설정 값이 필요한 곳에서는 항상 ``get_settings()`` 를 쓴다 (프로세스당 1회 생성).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 앱 ---
    app_name: str = "SpecCheck AI"
    app_version: str = "1.2.0"
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000,"
        "http://localhost:8787,http://127.0.0.1:8787,http://[::1]:8787"
    )

    # --- 경로 ---
    data_dir: Path = BACKEND_DIR / "data"
    datasets_dir: Path = PROJECT_ROOT / "datasets"
    #: Agent가 업로드한 스냅샷 저장소 (M3)
    snapshot_db: Path = BACKEND_DIR / "data" / "snapshots.db"
    local_agent_backend_url: str = "http://127.0.0.1:8000"

    # --- 외부 API ---
    openai_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    #: 동일 모델의 가격 조회 결과를 짧게 보관해 API 호출량과 화면 대기 시간을 줄인다.
    naver_price_cache_ttl_seconds: int = 900
    ebay_app_id: str = ""

    # --- 게시글 품질 평가 (GPT-2 perplexity) ---
    #: 기본은 비활성. 모델을 저장소에 포함하지 않으므로 경로를 지정해야 동작한다.
    quality_eval_enabled: bool = False
    quality_model_dir: str = ""

    # --- Local LLM (Gemma 4, Ollama) ---
    #: 기본은 비활성. 활성화하면 Ollama의 Gemma로 진단 설명을 생성한다.
    llm_enabled: bool = False
    #: 진단/추천 설명의 기본 모델. E2B는 일반 데스크톱에서 쓸 수 있는 Gemma 4 양자화 태그다.
    llm_model: str = "gemma4:e2b"
    #: 기본 모델이 아직 설치되지 않았을 때만 사용하는 이전 로컬 모델.
    llm_fallback_model: str = "gemma3:4b"
    ollama_url: str = "http://127.0.0.1:11434"
    #: Gemma 4의 첫 추론과 구조화된 추천 응답을 위한 제한 시간.
    llm_timeout: float = 60.0
    llm_status_timeout: float = 1.5
    #: 진단 프롬프트는 작으므로 로컬 메모리를 보존하는 컨텍스트 상한을 둔다.
    llm_context_tokens: int = 8192
    llm_keep_alive: str = "10m"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
