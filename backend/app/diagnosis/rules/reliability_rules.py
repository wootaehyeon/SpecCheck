"""Reliability 축 진단 규칙 (M4, M2 telemetry 기반).

WHEA와 비정상 종료는 "느리다"는 체감 증상과 달리 **결함의 직접 증거**다.
증상이 아직 없어도 부품 교체 필요성을 예측할 수 있는 유일한 축이라,
What-if Scan과 M9 추세 예측의 출발점이 된다.

건수는 항상 ``window_days`` 관측 구간과 함께 해석한다. 같은 5건이라도
30일간 5건과 하루 5건은 전혀 다른 이야기다.
"""

from __future__ import annotations

from typing import Any

from app.diagnosis.engine import Rule, register
from app.schemas.diagnosis import ActionType, Axis, Evidence, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot

#: 정정된 WHEA 오류. 소수는 정상 동작 범위지만 누적되면 메모리/PCIe 링크 열화 신호다.
WHEA_CORRECTED_WARN = 5
WHEA_CORRECTED_HIGH = 20

#: 비정상 종료는 1~2회면 정전이나 강제 종료일 수 있다. 반복될 때만 결함으로 본다.
CRASH_REPEAT_THRESHOLD = 3

#: 디스크 IO 오류. 케이블/연결 불량으로도 나므로 적은 수는 점검부터 권한다.
DISK_ERROR_WARN = 1
DISK_ERROR_HIGH = 10


def _totals(snapshot: TelemetrySnapshot) -> dict[str, Any]:
    return snapshot.data("reliability").get("totals") or {}


def _window(snapshot: TelemetrySnapshot) -> int | None:
    return snapshot.data("reliability").get("window_days")


def _events(snapshot: TelemetrySnapshot, *categories: str) -> list[dict[str, Any]]:
    return [
        event
        for event in snapshot.data("reliability").get("events") or []
        if event.get("category") in categories
    ]


def _evidence(snapshot: TelemetrySnapshot, *categories: str) -> list[Evidence]:
    """EventID별 내역을 근거로 만든다.

    내역이 비어 있어도 집계(totals)만으로 판정이 성립하는 경우가 있으므로
    (구버전 Agent, 이벤트 목록이 잘린 스냅샷) 총계 근거로 대체한다.
    **근거가 하나도 없는 Finding은 만들지 않는다**는 것이 이 함수의 계약이다.
    """
    evidence = [
        Evidence(
            source="reliability.events",
            detail="{0} (Provider {1} / EventID {2}) {3}건, 최근 {4}".format(
                event.get("label"),
                event.get("provider"),
                event.get("event_id"),
                event.get("count"),
                event.get("last_at"),
            ),
            value=event,
        )
        for event in _events(snapshot, *categories)
    ]
    if evidence:
        return evidence

    totals = _totals(snapshot)
    counts = {category: totals.get(category) or 0 for category in categories}
    return [
        Evidence(
            source="reliability.totals",
            detail="최근 {0}일 집계: {1}".format(
                _window(snapshot),
                ", ".join("{0} {1}건".format(name, count) for name, count in counts.items()),
            ),
            value=counts,
        )
    ]


def _coverage_confidence(snapshot: TelemetrySnapshot, base: float) -> float:
    """이벤트 로그가 관측 구간을 다 덮지 못하면 확신을 낮춘다.

    로그가 회전(rotate)돼 잘렸다면 실제 건수는 관측치보다 많을 수 있다.
    """
    covers = snapshot.data("reliability").get("log_covers_window")
    return base if covers is not False else round(base * 0.8, 2)


@register
class WheaFatalError(Rule):
    """치명적 하드웨어 오류(WHEA 18)."""

    rule_id = "RL-WHEA-002"
    title = "치명적 하드웨어 오류 발생"
    requires = ("reliability",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        count = _totals(snapshot).get("whea_fatal") or 0
        if count < 1:
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.CRITICAL,
            summary="최근 {0}일간 정정할 수 없는 하드웨어 오류가 {1}건 기록됐습니다.".format(
                _window(snapshot), count
            ),
            root_cause=(
                "CPU, 메모리, PCIe 장치 중 하나가 정정 불가능한 오류를 냈습니다. "
                "운영체제나 드라이버가 아니라 부품 자체의 결함 신호입니다."
            ),
            recommended_action=ActionType.PURCHASE,
            action_detail=(
                "메모리를 한 개씩 분리해 어느 모듈에서 재현되는지 확인하고(MemTest86 권장), "
                "특정 부품이 지목되면 교체하세요. 오버클럭/XMP를 사용 중이면 먼저 해제해 "
                "설정 문제인지 부품 결함인지 가려야 합니다."
            ),
            evidence=_evidence(snapshot, "whea_fatal"),
            confidence=_coverage_confidence(snapshot, 0.95),
        )


@register
class WheaCorrectedAccumulating(Rule):
    """정정된 WHEA 오류 누적.

    아직 증상이 없어도 부품이 열화하고 있다는 신호다. 다만 원인이 XMP/오버클럭
    같은 설정인 경우도 많아서, 낮은 구간에서는 구매가 아니라 설정 조치를 권한다.
    """

    rule_id = "RL-WHEA-001"
    title = "정정된 하드웨어 오류 누적"
    requires = ("reliability",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        count = _totals(snapshot).get("whea_corrected") or 0
        if count < WHEA_CORRECTED_WARN:
            return None

        severe = count >= WHEA_CORRECTED_HIGH

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH if severe else Severity.MEDIUM,
            summary="최근 {0}일간 정정된 하드웨어 오류가 {1}건 기록됐습니다.".format(
                _window(snapshot), count
            ),
            root_cause=(
                "메모리나 PCIe 링크에서 발생한 오류를 하드웨어가 자동으로 정정했습니다. "
                "지금은 데이터가 보존되지만, 정정 빈도가 늘어난다는 것은 해당 부품이 "
                "동작 한계에 가까워지고 있다는 뜻입니다."
            ),
            recommended_action=ActionType.PURCHASE if severe else ActionType.FIX,
            action_detail=(
                "MemTest86으로 메모리를 검증하고 오류가 재현되는 모듈을 교체하세요."
                if severe
                else "먼저 BIOS에서 XMP/EXPO를 해제하고 메모리를 다시 장착해 보세요. "
                "설정이나 접촉 불량이 원인이면 부품 교체 없이 사라집니다. "
                "그래도 계속 쌓이면 그때 교체를 검토하세요."
            ),
            evidence=_evidence(snapshot, "whea_corrected"),
            confidence=_coverage_confidence(snapshot, 0.85 if severe else 0.75),
        )


@register
class RepeatedUnexpectedShutdown(Rule):
    """비정상 종료 / 블루스크린 반복.

    원인이 드라이버, 전원 공급, 발열, 부품 결함 중 무엇인지는 이 규칙만으로
    가릴 수 없다. 그래서 구매가 아니라 원인 규명을 권한다 - 무엇을 살지 모르는
    상태에서 구매를 권하는 것은 조언이 아니다. 인과 추정은 M7이 맡는다.
    """

    rule_id = "RL-CRASH-001"
    title = "비정상 종료가 반복됨"
    requires = ("reliability",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        totals = _totals(snapshot)
        shutdowns = totals.get("unexpected_shutdown") or 0
        bugchecks = totals.get("bugcheck") or 0
        count = shutdowns + bugchecks
        if count < CRASH_REPEAT_THRESHOLD:
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.SOFTWARE,
            severity=Severity.HIGH,
            summary="최근 {0}일간 비정상 종료 {1}건, 블루스크린 {2}건이 기록됐습니다.".format(
                _window(snapshot), shutdowns, bugchecks
            ),
            root_cause=(
                "정상 종료 절차 없이 시스템이 멈췄습니다. 드라이버 충돌, 전원 공급 부족, "
                "과열, 메모리 오류가 모두 같은 증상을 냅니다. 어느 쪽인지는 추가 근거가 필요합니다."
            ),
            recommended_action=ActionType.FIX,
            action_detail=(
                "먼저 그래픽/칩셋 드라이버를 최신으로 올리고 Windows 업데이트를 적용하세요. "
                "그다음 이벤트 뷰어에서 중지 코드(BugCheck)를 확인하면 원인 부품이 좁혀집니다. "
                "지금 단계에서 부품을 사는 것은 이릅니다."
            ),
            evidence=_evidence(snapshot, "unexpected_shutdown", "bugcheck"),
            confidence=_coverage_confidence(snapshot, 0.8),
        )


@register
class DiskIoErrors(Rule):
    """디스크 IO 오류 이벤트.

    SMART이 깨끗해도 이 이벤트가 쌓이면 매체가 아니라 연결(케이블/포트/전원)이
    원인인 경우가 많다. 그래서 적은 건수에서는 점검을 먼저 권한다.
    """

    rule_id = "RL-DISK-001"
    title = "디스크 입출력 오류 기록"
    requires = ("reliability",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        totals = _totals(snapshot)
        count = (totals.get("disk_error") or 0) + (totals.get("filesystem_error") or 0)
        if count < DISK_ERROR_WARN:
            return None

        severe = count >= DISK_ERROR_HIGH

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH if severe else Severity.MEDIUM,
            summary="최근 {0}일간 디스크 입출력 오류가 {1}건 기록됐습니다.".format(
                _window(snapshot), count
            ),
            root_cause=(
                "저장장치 읽기/쓰기가 실패해 재시도됐습니다. 매체 손상, 케이블/포트 접촉 불량, "
                "전원 부족이 모두 원인이 될 수 있습니다."
            ),
            recommended_action=ActionType.PURCHASE if severe else ActionType.FIX,
            action_detail=(
                "백업 후 저장장치를 교체하세요. 이 빈도에서는 연결 문제만으로 보기 어렵습니다."
                if severe
                else "SATA/전원 케이블을 다시 연결하고 다른 포트로 바꿔 보세요. "
                "chkdsk로 파일 시스템을 점검한 뒤 재발 여부를 확인하면 매체 문제인지 갈립니다."
            ),
            evidence=_evidence(snapshot, "disk_error", "filesystem_error"),
            confidence=_coverage_confidence(snapshot, 0.85 if severe else 0.7),
        )
