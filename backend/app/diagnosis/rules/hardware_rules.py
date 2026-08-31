"""Hardware 축 진단 규칙 (M4).

여기 있는 규칙들은 M1(Hardware Inventory)만으로 판정 가능한 것들이다.
M2(성능/WHEA/저장장치 상태)가 붙으면 발열 스로틀링, 디스크 수명 같은
더 강한 근거의 규칙이 추가된다.
"""

from __future__ import annotations

from app.diagnosis.engine import Rule, register
from app.schemas.diagnosis import ActionType, Axis, Evidence, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot

#: 이 값 미만이면 일반적인 웹/문서 작업에서도 체감 병목이 발생한다.
MIN_COMFORTABLE_RAM_GB = 8.0
#: 정격 대비 이 비율 아래로 동작하면 XMP/EXPO 미적용으로 본다.
#: 노트북 온보드 LPDDR은 정격보다 한 단계 낮게 동작하는 경우가 정상이라
#: (예: 6400 정격 / 6000 동작) 10% 여유를 둬 오탐을 막는다.
RAM_SPEED_TOLERANCE = 0.90


@register
class RamSpeedNotApplied(Rule):
    """메모리가 정격보다 느리게 동작 중.

    XMP/EXPO 프로파일을 켜지 않으면 메모리가 JEDEC 기본 클럭으로 돈다.
    돈을 더 쓸 필요 없이 BIOS 설정만으로 되찾을 수 있는 성능이라,
    "구매하지 않아도 되는" 대표 사례다.
    """

    rule_id = "HW-RAM-001"
    title = "메모리가 정격 속도로 동작하지 않음"

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        modules = (snapshot.data("hardware").get("memory") or {}).get("modules") or []

        slow = []
        for index, module in enumerate(modules):
            rated = module.get("rated_speed_mhz")
            configured = module.get("configured_speed_mhz")
            if not rated or not configured:
                continue
            if configured < rated * RAM_SPEED_TOLERANCE:
                slow.append((index, module, rated, configured))

        if not slow:
            return None

        index, _module, rated, configured = slow[0]
        loss_percent = round((1 - configured / rated) * 100)

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.MEDIUM if loss_percent >= 20 else Severity.LOW,
            summary="메모리가 정격 {0}MHz 대신 {1}MHz로 동작 중입니다 (약 {2}% 손실).".format(
                rated, configured, loss_percent
            ),
            root_cause="BIOS에서 XMP/EXPO 프로파일이 활성화되지 않아 JEDEC 기본 클럭으로 동작하고 있습니다.",
            recommended_action=ActionType.FIX,
            action_detail=(
                "BIOS 설정에서 XMP(Intel) 또는 EXPO(AMD) 프로파일을 활성화하세요. "
                "부품 교체는 필요하지 않습니다. 메모리가 기판에 납땜된 노트북은 해당하지 않습니다."
            ),
            evidence=[
                Evidence(
                    source="hardware.memory.modules[{0}]".format(idx),
                    detail="슬롯 {0}: 정격 {1}MHz / 실제 {2}MHz".format(
                        module.get("slot") or idx, rated_mhz, configured_mhz
                    ),
                    value={"rated_speed_mhz": rated_mhz, "configured_speed_mhz": configured_mhz},
                )
                for idx, module, rated_mhz, configured_mhz in slow
            ],
            confidence=0.9,
        )


@register
class SystemDiskIsHdd(Rule):
    """시스템 드라이브가 HDD.

    체감 성능에 가장 큰 영향을 주면서, SSD 교체 비용이 가장 저렴한 항목이다.
    CPU/GPU 업그레이드보다 우선순위가 높다.
    """

    rule_id = "HW-DISK-001"
    title = "시스템 드라이브가 HDD"

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        disks = snapshot.data("hardware").get("storage") or []
        if not disks:
            return None

        # Win32_DiskDrive의 Index 0이 통상 부팅 디스크다.
        # M2에서 Win32_LogicalDisk 연결이 붙으면 정확한 시스템 볼륨으로 교체한다.
        primary = disks[0]
        if primary.get("media_type") != "HDD":
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH,
            summary="시스템 드라이브가 HDD({0})입니다. 부팅과 프로그램 실행이 전반적으로 느립니다.".format(
                primary.get("model")
            ),
            root_cause="OS가 설치된 저장장치의 임의 접근 속도가 SSD 대비 수십 배 느립니다.",
            recommended_action=ActionType.PURCHASE,
            action_detail="NVMe SSD로 교체하면 CPU/GPU 교체보다 적은 비용으로 체감 성능이 가장 크게 개선됩니다.",
            evidence=[
                Evidence(
                    source="hardware.storage[0]",
                    detail="{0} / {1}GB / {2}".format(
                        primary.get("model"), primary.get("size_gb"), primary.get("interface")
                    ),
                    value=primary,
                )
            ],
            confidence=0.85,
        )


@register
class InsufficientMemory(Rule):
    """물리 메모리 부족."""

    rule_id = "HW-RAM-002"
    title = "물리 메모리 부족"

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        memory = snapshot.data("hardware").get("memory") or {}
        total = memory.get("total_gb")
        if total is None or total >= MIN_COMFORTABLE_RAM_GB:
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH,
            summary="전체 메모리가 {0}GB로, 일반적인 작업에도 부족합니다.".format(total),
            root_cause="메모리가 부족하면 OS가 디스크 페이징에 의존하게 되어 전체 반응 속도가 떨어집니다.",
            recommended_action=ActionType.PURCHASE,
            action_detail="{0}GB 이상으로 증설하세요. 빈 슬롯이 있으면 기존 모듈을 유지한 채 추가할 수 있습니다.".format(
                int(MIN_COMFORTABLE_RAM_GB)
            ),
            evidence=[
                Evidence(
                    source="hardware.memory",
                    detail="총 {0}GB / 모듈 {1}개".format(total, memory.get("module_count")),
                    value={"total_gb": total, "module_count": memory.get("module_count")},
                )
            ],
            confidence=0.9,
        )
