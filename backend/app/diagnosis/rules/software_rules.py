"""Software 축 진단 규칙 (M4).

"느려졌다"의 원인이 부품 노후가 아니라 소프트웨어 상태인 경우를 잡아낸다.
이 축의 Finding이 많다는 것은 곧 구매하지 않아도 된다는 뜻이므로,
No-Purchase Scenario를 뒷받침하는 가장 중요한 축이다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.diagnosis.engine import Rule, register
from app.schemas.diagnosis import ActionType, Axis, Evidence, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot

#: 그래픽 드라이버가 이 기간 이상 방치되면 게임/영상 작업에서 성능·안정성 손해가 누적된다.
STALE_DRIVER_DAYS = 730
#: BIOS/펌웨어 노후 기준. 보안 패치와 CPU 마이크로코드 갱신이 걸려 있다.
STALE_BIOS_DAYS = 1095


def _days_since(value: object) -> int | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).days


@register
class StaleGpuDriver(Rule):
    """그래픽 드라이버 노후."""

    rule_id = "SW-GPU-001"
    title = "그래픽 드라이버가 오래됨"

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        gpus = snapshot.data("hardware").get("gpu") or []
        if not gpus:
            return None

        stale = []
        for gpu in gpus:
            days = _days_since(gpu.get("driver_date"))
            if days is not None and days >= STALE_DRIVER_DAYS:
                stale.append((gpu, days))

        if not stale:
            return None

        gpu, days = max(stale, key=lambda item: item[1])
        years = round(days / 365, 1)

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.SOFTWARE,
            severity=Severity.MEDIUM,
            summary="{0}의 드라이버가 약 {1}년 전 버전입니다.".format(gpu.get("name"), years),
            root_cause="드라이버가 최신 게임/애플리케이션의 최적화 프로파일과 버그 수정을 반영하지 못하고 있습니다.",
            recommended_action=ActionType.FIX,
            action_detail="제조사(NVIDIA/AMD/Intel) 공식 드라이버를 최신 버전으로 설치하세요. 무료이며 부품 교체보다 먼저 시도할 조치입니다.",
            evidence=[
                Evidence(
                    source="hardware.gpu",
                    detail="{0} / 드라이버 {1} ({2})".format(
                        item.get("name"), item.get("driver_version"), item.get("driver_date")
                    ),
                    value={"driver_date": item.get("driver_date"), "days_old": age},
                )
                for item, age in stale
            ],
            confidence=0.75,
        )


@register
class StaleBios(Rule):
    """BIOS/펌웨어 노후."""

    rule_id = "SW-BIOS-001"
    title = "BIOS 펌웨어가 오래됨"

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        bios = (snapshot.data("hardware").get("motherboard") or {}).get("bios") or {}
        days = _days_since(bios.get("released_at"))
        if days is None or days < STALE_BIOS_DAYS:
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.SOFTWARE,
            severity=Severity.LOW,
            summary="BIOS 버전 {0}이 약 {1}년 전 릴리스입니다.".format(
                bios.get("version"), round(days / 365, 1)
            ),
            root_cause="펌웨어에 포함되는 CPU 마이크로코드 갱신과 보안 패치가 적용되지 않은 상태입니다.",
            recommended_action=ActionType.FIX,
            action_detail="메인보드 제조사 지원 페이지에서 최신 BIOS를 확인하세요. 업데이트 중 전원이 끊기면 보드가 손상될 수 있으므로 주의가 필요합니다.",
            evidence=[
                Evidence(
                    source="hardware.motherboard.bios",
                    detail="{0} {1} ({2})".format(
                        bios.get("manufacturer"), bios.get("version"), bios.get("released_at")
                    ),
                    value=bios,
                )
            ],
            confidence=0.7,
        )
