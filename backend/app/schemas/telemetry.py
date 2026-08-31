"""Telemetry 스냅샷 스키마 (Backend 측 계약).

원본 정의: ``shared/contracts/telemetry_snapshot.schema.json``
생산자 구현: ``agent/speccheck_agent/snapshot.py``

Agent와 Backend는 이 형식으로만 대화한다. 필드를 바꾸려면 계약 파일부터
고치고 세 곳(계약, Agent, Backend)을 함께 갱신한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

#: Backend가 수용하는 스냅샷 스키마 MAJOR 버전.
#: 이보다 높은 MAJOR가 오면 Agent 업데이트 없이는 해석할 수 없으므로 거절한다.
SUPPORTED_SCHEMA_MAJOR = 1

ScanMode = Literal["actual", "estimated"]
SectionStatus = Literal["ok", "partial", "skipped", "planned", "error"]

#: 진단 규칙이 근거로 쓸 수 있는 섹션 상태
USABLE_STATUSES: tuple[SectionStatus, ...] = ("ok", "partial")


class AgentInfo(BaseModel):
    version: str
    os: str
    os_version: str | None = None
    python: str | None = None


class Section(BaseModel):
    """collector 하나의 실행 결과."""

    status: SectionStatus
    milestone: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """진단 근거로 사용할 수 있는지."""
        return self.status in USABLE_STATUSES


class TelemetrySnapshot(BaseModel):
    schema_version: str
    snapshot_id: str
    collected_at: datetime
    scan_mode: ScanMode
    device_id: str | None = None
    agent: AgentInfo
    sections: dict[str, Section] = Field(default_factory=dict)
    notes: str | None = None

    @property
    def schema_major(self) -> int:
        try:
            return int(self.schema_version.split(".")[0])
        except (ValueError, IndexError):
            return -1

    def section(self, name: str) -> Section | None:
        """사용 가능한 섹션만 반환한다. 실패/미구현 섹션은 None."""
        section = self.sections.get(name)
        return section if section and section.usable else None

    def data(self, name: str) -> dict[str, Any]:
        """섹션 데이터를 반환한다. 없으면 빈 dict."""
        section = self.section(name)
        return section.data if section else {}

    def coverage(self) -> dict[str, SectionStatus]:
        """어떤 telemetry가 실제로 확보됐는지. 진단 신뢰도의 근거가 된다."""
        return {name: section.status for name, section in self.sections.items()}


class SnapshotAccepted(BaseModel):
    """업로드 응답."""

    snapshot_id: str
    scan_mode: ScanMode
    received_at: datetime
    usable_sections: list[str]
    message: str = "스냅샷을 저장했습니다."


class SnapshotSummary(BaseModel):
    snapshot_id: str
    device_id: str | None
    collected_at: datetime
    scan_mode: ScanMode
    agent_version: str | None
    coverage: dict[str, str]
