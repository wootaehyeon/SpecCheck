"""ML diagnosis orchestration and offline teacher registry.

Rule.evaluate is only used by training; live diagnosis loads fitted model artifacts.
Action aggregation and data-availability checks are application policies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.schemas.diagnosis import (
    ACTION_WEIGHT,
    SEVERITY_WEIGHT,
    ActionDecision,
    ActionType,
    DiagnosisResult,
    Finding,
)
from app.schemas.telemetry import TelemetrySnapshot


class Rule(ABC):
    """진단 규칙 하나."""

    #: 안정적인 식별자. 리포트/피드백에서 규칙을 추적하는 키이므로 바꾸지 않는다.
    rule_id: str = "R000"
    title: str = ""
    #: 이 규칙이 근거로 쓰는 스냅샷 섹션들. 하나라도 없으면 규칙은 실행되지 않는다.
    requires: tuple[str, ...] = ("hardware",)

    def applicable(self, snapshot: TelemetrySnapshot) -> bool:
        return all(snapshot.section(name) is not None for name in self.requires)

    @abstractmethod
    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        """이상 없으면 None을 반환한다."""


_REGISTRY: dict[str, type[Rule]] = {}


def register(cls: type[Rule]) -> type[Rule]:
    if cls.rule_id in _REGISTRY:
        raise ValueError("rule_id 중복: {0}".format(cls.rule_id))
    _REGISTRY[cls.rule_id] = cls
    return cls


def registry() -> dict[str, type[Rule]]:
    return dict(_REGISTRY)


def _coverage_confidence(snapshot: TelemetrySnapshot) -> float:
    """확보된 telemetry 비중.

    ``planned``(미구현) 섹션은 사용자 환경 탓이 아니므로 분모에서 제외한다.
    구현된 collector 중 몇 개가 실제로 성공했는지만 본다.
    """
    statuses = [
        section.status
        for section in snapshot.sections.values()
        if section.status != "planned"
    ]
    if not statuses:
        return 0.0
    usable = sum(1 for status in statuses if status in ("ok", "partial"))
    base = usable / len(statuses)
    # Estimated Scan은 실측이 아니라 추정치이므로 신뢰도를 낮춰 잡는다.
    return round(base * (1.0 if snapshot.scan_mode == "actual" else 0.6), 2)


def decide(findings: list[Finding]) -> ActionDecision:
    """Finding들로부터 유지/수정/구매를 고른다.

    같은 문제를 더 싼 방법으로 해결할 수 있으면 그쪽을 택한다는 원칙에 따라,
    구매 권고는 그것을 요구하는 Finding이 실제로 있을 때만 나온다.
    """
    if not findings:
        return ActionDecision(
            action=ActionType.KEEP,
            reason="수집된 정보에서 조치가 필요한 이상 징후를 찾지 못했습니다. 지금 구매할 이유가 없습니다.",
        )

    strongest = max(findings, key=lambda f: ACTION_WEIGHT[f.recommended_action])
    action = strongest.recommended_action
    driven_by = [f.rule_id for f in findings if f.recommended_action == action]

    if action is ActionType.FIX:
        reason = "설정/소프트웨어 조치로 해결 가능한 문제가 {0}건 발견됐습니다. 부품 구매 없이 개선할 수 있습니다.".format(
            len(driven_by)
        )
    elif action is ActionType.PURCHASE:
        reason = "소프트웨어 조치로는 해결되지 않는 문제가 {0}건 있어 부품 교체를 권고합니다.".format(
            len(driven_by)
        )
    else:
        reason = "발견된 항목은 모두 참고 수준이며 즉시 조치가 필요하지 않습니다."

    return ActionDecision(action=action, reason=reason, driven_by=driven_by)


def diagnose(snapshot: TelemetrySnapshot, rule_ids: list[str] | None = None) -> DiagnosisResult:
    """Run the trained models. Legacy rules are offline training teachers only."""
    from app.diagnosis.ml import model_version, predict_findings

    findings = predict_findings(snapshot, rule_ids)

    # 심각한 것부터, 같은 심각도면 확신이 높은 것부터
    findings.sort(
        key=lambda f: (SEVERITY_WEIGHT[f.severity], f.confidence),
        reverse=True,
    )

    return DiagnosisResult(
        snapshot_id=snapshot.snapshot_id,
        scan_mode=snapshot.scan_mode,
        generated_at=datetime.now(timezone.utc),
        findings=findings,
        decision=decide(findings),
        coverage=snapshot.coverage(),
        confidence=_coverage_confidence(snapshot),
        inference_method="machine_learning",
        model_version=model_version(),
        training_label_source="legacy_rule_weak_supervision",
    )
