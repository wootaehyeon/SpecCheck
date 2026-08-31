"""진단 결과 스키마.

SpecCheck의 진단은 "무엇을 사라"가 아니라 "왜 사야 하는가 / 안 사도 되는가"를
답한다. 그래서 모든 Finding은 근거(Evidence)와 권장 행동(ActionType)을
반드시 함께 갖는다. 근거 없는 결론은 만들지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Axis(str, Enum):
    """이상 징후의 3축 분류."""

    HARDWARE = "hardware"
    SOFTWARE = "software"
    SECURITY = "security"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    """Action Decision의 세 갈래."""

    KEEP = "keep"  # 유지한다 - No-Purchase Scenario
    FIX = "fix"  # 수정한다 - Software Fix / 설정 변경
    PURCHASE = "purchase"  # 구매한다 - 부품 교체


#: 행동의 강도 순서. 여러 Finding이 나왔을 때 최종 결정을 고르는 기준이며,
#: 값이 클수록 사용자 비용이 크다. 같은 문제를 해결할 수 있다면 낮은 쪽을 택한다.
ACTION_WEIGHT: dict[ActionType, int] = {
    ActionType.KEEP: 0,
    ActionType.FIX: 1,
    ActionType.PURCHASE: 2,
}

SEVERITY_WEIGHT: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class Evidence(BaseModel):
    """Finding을 뒷받침하는 실측값 하나."""

    source: str = Field(description="telemetry 출처. 예) hardware.memory.modules[0]")
    detail: str = Field(description="사람이 읽는 설명")
    value: Any = None


class Finding(BaseModel):
    """규칙 하나가 찾아낸 이상 징후."""

    rule_id: str
    title: str
    axis: Axis
    severity: Severity
    summary: str
    root_cause: str | None = Field(default=None, description="증상이 아닌 근본 원인")
    recommended_action: ActionType
    action_detail: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ActionDecision(BaseModel):
    """유지 / 수정 / 구매 중 최종 권고."""

    action: ActionType
    reason: str
    driven_by: list[str] = Field(default_factory=list, description="근거가 된 rule_id 목록")


class DiagnosisResult(BaseModel):
    snapshot_id: str
    scan_mode: str
    generated_at: datetime
    findings: list[Finding] = Field(default_factory=list)
    decision: ActionDecision
    coverage: dict[str, str] = Field(
        default_factory=dict, description="섹션별 수집 상태. 진단 신뢰도의 근거"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="확보된 telemetry 비중 기반 종합 신뢰도"
    )
    explanation: str | None = Field(default=None, description="LLM이 생성한 자연어 설명 (M5)")
