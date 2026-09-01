"""Storage 축 진단 규칙 (M4, M2 telemetry 기반).

``storage_health`` 섹션이 있어야 동작한다. 섹션이 없으면(Agent 미설치,
관리자 권한 없음, 구버전 Agent) 이 규칙들은 **조용히 실행되지 않는다.**
"디스크가 멀쩡하다"가 아니라 "디스크를 보지 못했다"가 맞는 표현이기 때문이며,
그 사실은 DiagnosisResult의 coverage/confidence에 반영된다.

여유 공간 규칙이 맨 앞에 있는 이유: 체감 성능 저하의 가장 흔한 원인이면서
해결에 돈이 들지 않는다. No-Purchase Scenario의 대표 사례다.
"""

from __future__ import annotations

from typing import Any

from app.diagnosis.engine import Rule, register
from app.schemas.diagnosis import ActionType, Axis, Evidence, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot

#: Windows는 페이징·업데이트·조각 모음에 여유 공간을 쓴다. 이 아래로 내려가면
#: 디스크 성능 자체보다 공간 부족이 먼저 체감 성능을 깎는다.
LOW_FREE_PERCENT = 10.0
CRITICAL_FREE_PERCENT = 5.0
#: 비율만 보면 대용량 디스크에서 오탐이 난다(2TB의 8% = 160GB는 충분하다).
#: 절대량 조건을 함께 두어 둘 다 만족할 때만 문제로 본다.
LOW_FREE_GB = 40.0
CRITICAL_FREE_GB = 15.0

#: 대기 섹터(C5)는 아직 재할당되지 않은 불안정 섹터다. 값이 0을 넘는 순간부터
#: 데이터 손실 위험이 있어 재할당 섹터보다 급하다.
REALLOCATED_WARN = 1
REALLOCATED_HIGH = 10

#: 수명 소모율(%). 보증 수명은 하한선이지 고장 시점이 아니므로, 90% 전까지는
#: 교체가 아니라 백업과 계획을 권한다.
WEAR_PLAN_PERCENT = 70
WEAR_REPLACE_PERCENT = 90


def _disks(snapshot: TelemetrySnapshot) -> list[dict[str, Any]]:
    return snapshot.data("storage_health").get("disks") or []


def _system_volume(snapshot: TelemetrySnapshot) -> dict[str, Any]:
    for volume in snapshot.data("storage_health").get("volumes") or []:
        if volume.get("is_system"):
            return volume
    return {}


def _label(disk: dict[str, Any]) -> str:
    return disk.get("model") or "디스크 {0}".format(disk.get("index"))


@register
class SystemVolumeLowSpace(Rule):
    """시스템 드라이브 여유 공간 부족.

    새 SSD를 사기 전에 지울 것부터 지우는 편이 낫다. 이 규칙이 잡히면
    Action Decision은 구매가 아니라 정리로 간다.
    """

    rule_id = "ST-SPACE-001"
    title = "시스템 드라이브 여유 공간 부족"
    requires = ("storage_health",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        volume = _system_volume(snapshot)
        free_percent = volume.get("free_percent")
        free_gb = volume.get("free_gb")
        if free_percent is None or free_gb is None:
            return None

        # 비율과 절대량을 모두 넘어야 문제로 본다.
        if free_percent >= LOW_FREE_PERCENT or free_gb >= LOW_FREE_GB:
            return None

        critical = free_percent < CRITICAL_FREE_PERCENT or free_gb < CRITICAL_FREE_GB

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.SOFTWARE,
            severity=Severity.HIGH if critical else Severity.MEDIUM,
            summary="시스템 드라이브 {0} 여유 공간이 {1}GB({2}%)뿐입니다.".format(
                volume.get("drive"), free_gb, free_percent
            ),
            root_cause=(
                "Windows는 페이징 파일, 업데이트 임시 파일, 파일 시스템 여유 블록에 "
                "디스크 공간을 사용합니다. 여유가 부족하면 저장장치 성능과 무관하게 "
                "전체 반응 속도가 떨어지고 업데이트가 실패합니다."
            ),
            recommended_action=ActionType.FIX,
            action_detail=(
                "저장소 센스/디스크 정리로 임시 파일과 이전 Windows 설치본을 제거하고, "
                "큰 파일은 다른 드라이브로 옮기세요. 전체 용량의 15% 이상을 확보하는 것이 목표입니다. "
                "정리 후에도 부족하면 그때 증설을 검토하면 됩니다."
            ),
            evidence=[
                Evidence(
                    source="storage_health.volumes[system]",
                    detail="{0} {1}GB 중 {2}GB 여유 ({3}%)".format(
                        volume.get("drive"), volume.get("size_gb"), free_gb, free_percent
                    ),
                    value=volume,
                )
            ],
            confidence=0.95,
        )


@register
class DiskFailurePredicted(Rule):
    """SMART 실패 예측 플래그.

    디스크 펌웨어 자신이 임박한 고장을 보고한 상태다. 다른 어떤 근거보다 강하다.
    """

    rule_id = "ST-SMART-002"
    title = "저장장치가 임박한 고장을 보고함"
    requires = ("storage_health",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        failing = [disk for disk in _disks(snapshot) if disk.get("predict_failure")]
        if not failing:
            return None

        disk = failing[0]
        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.CRITICAL,
            summary="{0}의 SMART가 임박한 고장을 예측하고 있습니다.".format(_label(disk)),
            root_cause="저장장치 펌웨어가 자체 진단에서 임계값을 넘은 속성을 발견했습니다.",
            recommended_action=ActionType.PURCHASE,
            action_detail=(
                "지금 즉시 중요한 데이터를 백업하고 저장장치를 교체하세요. "
                "이 단계에서는 소프트웨어 조치로 되돌릴 수 없습니다."
            ),
            evidence=[
                Evidence(
                    source="storage_health.disks[{0}].predict_failure".format(item.get("index")),
                    detail="{0}: 실패 예측 (사유 코드 {1})".format(
                        _label(item), item.get("predict_failure_reason")
                    ),
                    value=item,
                )
                for item in failing
            ],
            confidence=0.98,
        )


@register
class BadSectorsGrowing(Rule):
    """재할당/대기 섹터 발생.

    대기 섹터(C5)는 아직 재할당되지 않은 읽기 불안정 섹터다. 재할당 섹터보다
    데이터 손실에 가깝기 때문에 한 개만 있어도 심각도를 올린다.
    """

    rule_id = "ST-SMART-001"
    title = "저장장치에 불량 섹터 발생"
    requires = ("storage_health",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        affected = []
        for disk in _disks(snapshot):
            reallocated = disk.get("reallocated_sectors")
            pending = disk.get("pending_sectors")
            if (reallocated or 0) >= REALLOCATED_WARN or (pending or 0) > 0:
                affected.append(disk)

        if not affected:
            return None

        worst = max(
            affected,
            key=lambda disk: ((disk.get("pending_sectors") or 0), (disk.get("reallocated_sectors") or 0)),
        )
        pending = worst.get("pending_sectors") or 0
        reallocated = worst.get("reallocated_sectors") or 0
        severe = pending > 0 or reallocated >= REALLOCATED_HIGH

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH if severe else Severity.MEDIUM,
            summary="{0}에 재할당 섹터 {1}개, 대기 섹터 {2}개가 기록돼 있습니다.".format(
                _label(worst), reallocated, pending
            ),
            root_cause=(
                "저장 매체의 물리적 손상입니다. 컨트롤러가 손상된 섹터를 예비 영역으로 "
                "옮기고 있으며, 예비 영역이 소진되면 데이터 손실로 이어집니다."
            ),
            recommended_action=ActionType.PURCHASE if severe else ActionType.FIX,
            action_detail=(
                "즉시 백업하고 저장장치 교체를 준비하세요. 불량 섹터는 되돌아가지 않습니다."
                if severe
                else "우선 백업 주기를 짧게 하고 값의 증가 추이를 관찰하세요. "
                "수치가 늘어나면 교체가 필요하지만, 멈춰 있으면 계속 사용할 수 있습니다."
            ),
            evidence=[
                Evidence(
                    source="storage_health.disks[{0}].smart".format(disk.get("index")),
                    detail="{0}: 재할당 {1} / 대기 {2} / 정정불가 {3}".format(
                        _label(disk),
                        disk.get("reallocated_sectors"),
                        disk.get("pending_sectors"),
                        disk.get("uncorrectable_sectors"),
                    ),
                    value={
                        "reallocated_sectors": disk.get("reallocated_sectors"),
                        "pending_sectors": disk.get("pending_sectors"),
                        "uncorrectable_sectors": disk.get("uncorrectable_sectors"),
                    },
                )
                for disk in affected
            ],
            confidence=0.9,
        )


@register
class SsdWearHigh(Rule):
    """SSD/NVMe 수명 소모.

    보증 수명(TBW)은 고장 시점이 아니라 제조사가 보증하는 하한이다. 그래서
    90% 전까지는 "지금 사라"가 아니라 "백업하고 계획하라"가 정확한 조언이다.
    """

    rule_id = "ST-WEAR-001"
    title = "저장장치 수명 소모"
    requires = ("storage_health",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        worn = [
            disk
            for disk in _disks(snapshot)
            if (disk.get("wear_percent") or 0) >= WEAR_PLAN_PERCENT
        ]
        if not worn:
            return None

        disk = max(worn, key=lambda item: item.get("wear_percent") or 0)
        wear = disk.get("wear_percent")
        replace = wear >= WEAR_REPLACE_PERCENT

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH if replace else Severity.MEDIUM,
            summary="{0}의 수명이 {1}% 소모됐습니다.".format(_label(disk), wear),
            root_cause=(
                "NAND 플래시는 쓰기 횟수에 수명이 있습니다. 누적 쓰기량이 보증 수명(TBW)에 "
                "가까워지면 예비 블록이 줄고 쓰기 성능과 안정성이 떨어집니다."
            ),
            recommended_action=ActionType.PURCHASE if replace else ActionType.KEEP,
            action_detail=(
                "교체를 준비하세요. 보증 수명을 넘긴 상태에서는 갑작스러운 읽기 전용 전환이 발생할 수 있습니다."
                if replace
                else "아직 교체할 단계는 아닙니다. 정기 백업을 확보하고 다음 스캔에서 소모율 증가 속도를 확인하세요."
            ),
            evidence=[
                Evidence(
                    source="storage_health.disks[{0}]".format(disk.get("index")),
                    detail="{0}: 소모율 {1}% / 통전 {2}시간 / 누적 쓰기 {3}TB".format(
                        _label(disk), wear, disk.get("power_on_hours"), disk.get("host_writes_tb")
                    ),
                    value={
                        "wear_percent": wear,
                        "power_on_hours": disk.get("power_on_hours"),
                        "host_writes_tb": disk.get("host_writes_tb"),
                    },
                )
            ],
            confidence=0.85,
        )
