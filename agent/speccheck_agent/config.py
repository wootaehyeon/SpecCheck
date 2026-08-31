"""Agent 실행 설정.

우선순위: CLI 인자 > 환경변수 > 기본값
모든 환경변수는 ``SPECCHECK_`` 접두사를 쓴다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _home() -> Path:
    """스냅샷 DB와 로그가 저장되는 로컬 디렉토리."""
    override = os.environ.get("SPECCHECK_AGENT_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".speccheck"


@dataclass
class AgentConfig:
    home: Path = field(default_factory=_home)
    backend_url: str = field(
        default_factory=lambda: os.environ.get("SPECCHECK_BACKEND_URL", "http://127.0.0.1:8000")
    )
    device_id: str | None = field(
        default_factory=lambda: os.environ.get("SPECCHECK_DEVICE_ID") or None
    )
    upload_timeout: float = 10.0

    @property
    def db_path(self) -> Path:
        return self.home / "agent.db"

    @property
    def snapshot_dir(self) -> Path:
        return self.home / "snapshots"

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
