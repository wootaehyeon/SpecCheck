"""UI-facing diagnosis 1.1 contract.

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


class AiDiagnosis(UiModel):
    provider: Literal["ollama", "template"]
    model: str
    status: Literal["generated", "fallback", "unavailable"]
    overview: str
    action_plan: list[str] = Field(alias="actionPlan")


class Decision(UiModel):
    action: ActionType
    reason: str
    driven_by: list[str] = Field(alias="drivenBy")


class UiDiagnosis(UiModel):
    schema_version: Literal["1.1.0"] = Field(default="1.1.0", alias="schemaVersion")
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
    ai: AiDiagnosis
    decision: Decision
