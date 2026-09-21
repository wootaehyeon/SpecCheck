"""UI-facing diagnosis 1.2 contract.

The rule engine keeps its snake_case domain model. These models define the
camelCase payload consumed by the diagnostics UI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.diagnosis import ActionType, Axis, Severity

HealthStatus = Literal["normal", "warning", "critical", "unknown"]
RiskLevel = Literal["low", "medium", "high", "critical"]
DiagnosisStatus = Literal["complete", "partial", "failed"]
SourceStatus = Literal["collected", "unavailable", "permission_required", "not_in_scope"]


class UiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Machine(UiModel):
    name: str
    os: str
    agent_version: str = Field(alias="agentVersion")


class Risk(UiModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    summary: str


class CategorySummary(UiModel):
    count: int = Field(ge=0)
    highest_severity: Severity = Field(alias="highestSeverity")
    summary: str


class Categories(UiModel):
    hardware: CategorySummary
    software: CategorySummary
    security: CategorySummary


class Resource(UiModel):
    key: str
    label: str
    value: float
    unit: str
    status: HealthStatus
    detail: str


class UiFinding(UiModel):
    id: str
    category: Axis
    code: str
    title: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: list[str]
    root_cause_candidates: list[str] = Field(alias="rootCauseCandidates")
    actions: list[str]
    recommended_action: ActionType = Field(alias="recommendedAction")


class InventoryItem(UiModel):
    kind: str
    name: str
    detail: str
    status: HealthStatus


class Source(UiModel):
    name: Literal["wmi", "cim", "whea", "storage", "performance", "sysmon"]
    status: SourceStatus
    collected_at: str | None = Field(alias="collectedAt")
    requirements: list["SourceRequirement"] = Field(default_factory=list)


class SourceRequirement(UiModel):
    title: str
    detail: str


class AiDiagnosis(UiModel):
    provider: Literal["ollama", "template"]
    model: str
    status: Literal["generated", "fallback", "unavailable"]
    overview: str
    action_plan: list[str] = Field(alias="actionPlan")


class RootCauseCandidate(UiModel):
    """Bounded M6 correlation result; never exposes raw Sysmon fields."""

    id: Literal["background_load", "hardware_instability"]
    rank: int = Field(ge=1, le=3)
    confidence: float = Field(ge=0.0, le=1.0)
    action: ActionType
    title: str
    summary: str
    evidence: list[str]
    limitation: str


class AnomalySignal(UiModel):
    """M7 state change signal; it remains separate from deterministic findings."""

    metric: str
    label: str
    direction: Literal["above_baseline", "below_baseline"]
    z_score: float = Field(alias="zScore")
    value: float
    baseline_mean: float = Field(alias="baselineMean")
    samples: int = Field(ge=3)


class AnomalyAnalysis(UiModel):
    status: Literal["no_signal", "signal_detected", "insufficient", "unavailable"]
    method: Literal["z_score"] | None = None
    evaluated_metrics: int = Field(default=0, alias="evaluatedMetrics", ge=0)
    required_baseline_samples: int = Field(default=3, alias="requiredBaselineSamples", ge=3)
    signals: list[AnomalySignal] = Field(default_factory=list)
    limitation: str


class TrajectoryTrend(UiModel):
    """M8 linear trend summary; dates are exploratory estimates, not failure dates."""

    metric: str
    label: str
    direction: Literal["improving", "stable", "worsening"]
    samples: int = Field(ge=3)
    slope_per_day: float = Field(alias="slopePerDay")
    threshold: float | None = None
    threshold_at: str | None = Field(default=None, alias="thresholdAt")
    threshold_range: list[str] | None = Field(default=None, alias="thresholdRange")


class TrajectoryAnalysis(UiModel):
    status: Literal["ready", "insufficient", "unavailable"]
    method: Literal["linear_regression"] | None = None
    required_samples: int = Field(default=3, alias="requiredSamples", ge=3)
    minimum_span_days: int = Field(default=1, alias="minimumSpanDays", ge=1)
    trends: list[TrajectoryTrend] = Field(default_factory=list)
    limitation: str


class Decision(UiModel):
    action: ActionType
    reason: str
    driven_by: list[str] = Field(alias="drivenBy")


class CompatibilityCheck(UiModel):
    label: str
    status: Literal["passed", "conditional", "failed"]
    detail: str


class CandidatePart(UiModel):
    key: str
    category: Literal["cpu", "motherboard", "memory", "storage"]
    name: str
    search_query: str = Field(alias="searchQuery")
    reason: str
    specifications: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, alias="sourceLabel")
    source_url: str | None = Field(default=None, alias="sourceUrl")


class ReplacementCandidate(UiModel):
    id: str
    strategy: Literal["minimal", "platform"]
    title: str
    summary: str
    recommended: bool
    compatibility_status: Literal["passed", "conditional"] = Field(alias="compatibilityStatus")
    compatibility_score: int = Field(alias="compatibilityScore", ge=0, le=100)
    checks: list[CompatibilityCheck]
    parts: list[CandidatePart]
    tradeoffs: list[str]


class RecommendationAiInsight(UiModel):
    provider: Literal["ollama", "template"]
    model: str
    status: Literal["generated", "fallback", "unavailable"]
    rationale: str
    cautions: list[str]


class Recommendation(UiModel):
    id: str
    finding_ids: list[str] = Field(alias="findingIds")
    priority: Literal["normal", "high", "urgent"]
    category: Literal["storage", "memory"]
    title: str
    description: str
    search_query: str = Field(alias="searchQuery")
    search_url: str = Field(alias="searchUrl")
    candidates: list[ReplacementCandidate]
    ai_insight: RecommendationAiInsight = Field(alias="aiInsight")


class UiDiagnosis(UiModel):
    schema_version: Literal["1.2.0"] = Field(default="1.2.0", alias="schemaVersion")
    scan_id: str = Field(alias="scanId")
    scan_type: Literal["basic"] = Field(default="basic", alias="scanType")
    status: DiagnosisStatus
    generated_at: str = Field(alias="generatedAt")
    machine: Machine
    risk: Risk
    categories: Categories
    resources: list[Resource]
    findings: list[UiFinding]
    inventory: list[InventoryItem]
    sources: list[Source]
    root_cause_candidates: list[RootCauseCandidate] = Field(default_factory=list, alias="rootCauseCandidates")
    anomaly_analysis: AnomalyAnalysis = Field(alias="anomalyAnalysis")
    trajectory_analysis: TrajectoryAnalysis = Field(alias="trajectoryAnalysis")
    ai: AiDiagnosis
    decision: Decision
    recommendations: list[Recommendation] = Field(default_factory=list)
