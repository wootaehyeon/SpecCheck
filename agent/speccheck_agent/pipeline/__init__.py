"""수집 결과 정규화 및 로컬 저장 (Phase 3 / M3)."""

from .normalize import to_spec_profile
from .store import SnapshotStore

__all__ = ["SnapshotStore", "to_spec_profile"]
