"""Performance 축 진단 규칙 (M4, M2 telemetry 기반).

샘플링 구간이 몇 초에 불과하다는 한계를 규칙이 스스로 인정해야 한다. 그래서
이 축의 규칙은 대부분 **평균과 최소를 함께** 본다. 최대만 높은 것은 스파이크이고,
최소까지 높아야 상시 부하다. 스파이크로 부품 교체를 권하는 것이 이 축에서
가장 흔한 오진이다.

같은 이유로 confidence를 다른 축보다 낮게 잡는다. 짧은 관측은 짧은 관측이다.
"""

from __future__ import annotations

from typing import Any

from app.diagnosis.engine import Rule, register
from app.schemas.diagnosis import ActionType, Axis, Evidence, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot

#: 커밋된 메모리 비율이 이 위로 가면 페이징이 시작된다.
MEMORY_COMMITTED_HIGH = 90.0
#: 가용 메모리 절대량. 비율만 보면 대용량 시스템에서 오탐이 난다.
MEMORY_AVAILABLE_LOW_MB = 1500.0

#: 상시 CPU 점유. 평균과 최소를 모두 넘어야 "쉬지 않는 부하"로 본다.
CPU_BUSY_AVG = 70.0
CPU_BUSY_MIN = 50.0

#: 부하가 있는데 클럭이 정격의 이 비율 아래면 스로틀링이나 전원 제한을 의심한다.
THROTTLE_CLOCK_RATIO = 0.6
THROTTLE_MIN_LOAD = 50.0
#: 온도가 확보된 경우의 위험 구간.
THERMAL_HIGH_C = 90.0


def _performance(snapshot: TelemetrySnapshot) -> dict[str, Any]:
    return snapshot.data("performance")


def _stat(block: dict[str, Any], path: str, key: str) -> float | None:
    """``cpu.usage_percent`` 같은 경로에서 avg/max/min 하나를 꺼낸다."""
    node: Any = block
    for part in path.split("."):
        node = (node or {}).get(part) if isinstance(node, dict) else None
    return (node or {}).get(key) if isinstance(node, dict) else None


@register
class MemoryPressure(Rule):
    """메모리 부족 (페이징 과다).

    실측 부하 기반이라 용량만 보는 ``HW-RAM-002`` 보다 근거가 강하다. 32GB를
    달고도 부족한 사용자와 8GB로 충분한 사용자를 구분할 수 있는 유일한 규칙이다.
    """

    rule_id = "PF-MEM-001"
    title = "메모리가 부족해 페이징이 발생 중"
    requires = ("performance",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        data = _performance(snapshot)
        committed = _stat(data, "memory.committed_percent", "avg")
        available = _stat(data, "memory.available_mb", "avg")
        if committed is None or available is None:
            return None

        # 두 신호가 함께 나타날 때만 판정한다. 커밋 비율만 높은 것은
        # 메모리를 넉넉히 예약한 애플리케이션 때문일 수 있다.
        if committed < MEMORY_COMMITTED_HIGH or available > MEMORY_AVAILABLE_LOW_MB:
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH,
            summary="측정 구간 동안 가용 메모리가 평균 {0}MB, 커밋 비율이 {1}%였습니다.".format(
                available, committed
            ),
            root_cause=(
                "물리 메모리가 모자라 OS가 페이지 파일(디스크)로 데이터를 밀어내고 있습니다. "
                "이 상태에서는 CPU나 GPU를 바꿔도 체감 속도가 개선되지 않습니다."
            ),
            recommended_action=ActionType.PURCHASE,
            action_detail=(
                "메모리 증설이 가장 효과가 큽니다. 먼저 시작 프로그램과 상주 프로그램을 정리해 "
                "여유가 생기는지 확인하고, 그래도 부족하면 빈 슬롯에 모듈을 추가하세요."
            ),
            evidence=[
                Evidence(
                    source="performance.memory",
                    detail="가용 평균 {0}MB / 최저 {1}MB / 커밋 {2}% / 페이징 {3}회 per sec".format(
                        available,
                        _stat(data, "memory.available_mb", "min"),
                        committed,
                        _stat(data, "memory.pages_per_sec", "avg"),
                    ),
                    value=data.get("memory"),
                )
            ],
            confidence=0.75,
        )


@register
class PowerSaverPlanActive(Rule):
    """전원 계획이 절전으로 고정됨.

    부품은 멀쩡한데 성능이 안 나오는 대표 사례이며, 클릭 몇 번으로 해결된다.
    """

    rule_id = "PF-POWER-001"
    title = "전원 계획이 절전 모드"
    requires = ("performance",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        power_plan = _performance(snapshot).get("power_plan") or {}
        if not power_plan.get("is_power_saver"):
            return None

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.SOFTWARE,
            severity=Severity.MEDIUM,
            summary="현재 전원 계획이 '{0}'으로 설정돼 있습니다.".format(
                power_plan.get("name") or "절전"
            ),
            root_cause=(
                "절전 계획은 CPU 최대 클럭을 의도적으로 제한합니다. 부품 성능과 무관하게 "
                "반응 속도와 프레임이 떨어집니다."
            ),
            recommended_action=ActionType.FIX,
            action_detail=(
                "설정 > 시스템 > 전원 및 배터리에서 전원 모드를 '균형 조정' 이상으로 바꾸세요. "
                "노트북이라면 충전기 연결 상태에서의 설정을 확인하면 됩니다. 비용은 들지 않습니다."
            ),
            evidence=[
                Evidence(
                    source="performance.power_plan",
                    detail="활성 계획: {0} ({1})".format(
                        power_plan.get("name"), power_plan.get("scheme")
                    ),
                    value=power_plan,
                )
            ],
            confidence=0.95,
        )


@register
class SustainedCpuLoad(Rule):
    """상시 CPU 점유 과다.

    "게임이 느려졌다"의 원인이 부품 노후가 아니라 백그라운드 프로그램인 경우를
    잡는다. 원인 프로세스를 지목할 수 있으면 조치는 구매가 아니라 정리다.
    """

    rule_id = "PF-CPU-001"
    title = "백그라운드 CPU 점유가 지속됨"
    requires = ("performance",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        data = _performance(snapshot)
        average = _stat(data, "cpu.usage_percent", "avg")
        lowest = _stat(data, "cpu.usage_percent", "min")
        if average is None or lowest is None:
            return None

        # 최소값까지 높아야 "쉬지 않는 부하"다. 최대만 높으면 스파이크이므로 침묵한다.
        if average < CPU_BUSY_AVG or lowest < CPU_BUSY_MIN:
            return None

        processes = data.get("top_processes") or []
        top = processes[0] if processes else {}

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.SOFTWARE,
            severity=Severity.HIGH,
            summary="유휴 상태여야 할 구간에서 CPU 점유율이 평균 {0}%(최저 {1}%)로 유지됐습니다.{2}".format(
                average,
                lowest,
                " 가장 높은 프로세스는 {0}입니다.".format(top.get("name")) if top else "",
            ),
            root_cause=(
                "특정 프로세스가 CPU를 계속 점유하고 있습니다. 부품 성능이 아니라 "
                "실행 중인 소프트웨어가 원인일 가능성이 큽니다."
            ),
            recommended_action=ActionType.FIX,
            action_detail=(
                "작업 관리자에서 해당 프로세스를 확인하세요. 업데이트·인덱싱·백신 검사처럼 "
                "일시적인 작업이면 끝날 때까지 기다리면 되고, 상시 실행되는 프로그램이면 "
                "시작 프로그램에서 제외하세요. 알 수 없는 프로세스라면 Advanced Scan으로 "
                "악성 소프트웨어 여부를 확인하는 것이 다음 단계입니다."
            ),
            evidence=[
                Evidence(
                    source="performance.cpu.usage_percent",
                    detail="평균 {0}% / 최저 {1}% / 최대 {2}%".format(
                        average, lowest, _stat(data, "cpu.usage_percent", "max")
                    ),
                    value=(data.get("cpu") or {}).get("usage_percent"),
                ),
                Evidence(
                    source="performance.top_processes",
                    detail=", ".join(
                        "{0} {1}%".format(item.get("name"), item.get("cpu_percent"))
                        for item in processes[:3]
                    )
                    or "프로세스 목록 없음",
                    value=processes[:3],
                ),
            ],
            # 관측 구간이 수 초에 불과하다. 상시 부하 여부는 재스캔으로 확인해야 한다.
            confidence=0.6,
        )


@register
class CpuThrottling(Rule):
    """부하 중 클럭 저하 (스로틀링 / 전원 제한).

    온도 센서가 없는 메인보드가 많아 온도만으로는 판정할 수 없다. 부하가 있는데도
    클럭이 정격보다 크게 낮다는 사실 자체를 간접 근거로 쓴다.
    """

    rule_id = "PF-THROTTLE-001"
    title = "부하 중 CPU 클럭이 정격보다 낮음"
    requires = ("performance",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        data = _performance(snapshot)
        clock = (data.get("cpu") or {}).get("clock") or {}
        ratio = clock.get("ratio")
        load = _stat(data, "cpu.usage_percent", "avg")
        if ratio is None or load is None:
            return None

        # 부하가 없을 때 클럭이 낮은 것은 정상적인 절전이다. 함께 봐야 의미가 있다.
        if ratio > THROTTLE_CLOCK_RATIO or load < THROTTLE_MIN_LOAD:
            return None

        thermal = data.get("thermal") or {}
        temperature = thermal.get("max_c")
        overheating = temperature is not None and temperature >= THERMAL_HIGH_C

        evidence = [
            Evidence(
                source="performance.cpu.clock",
                detail="현재 {0}MHz / 정격 {1}MHz (비율 {2}), CPU 부하 평균 {3}%".format(
                    clock.get("current_mhz"), clock.get("max_mhz"), ratio, load
                ),
                value=clock,
            )
        ]
        if thermal.get("available"):
            evidence.append(
                Evidence(
                    source="performance.thermal",
                    detail="측정된 최고 온도 {0}°C".format(temperature),
                    value=thermal,
                )
            )

        return Finding(
            rule_id=self.rule_id,
            title=self.title,
            axis=Axis.HARDWARE,
            severity=Severity.HIGH if overheating else Severity.MEDIUM,
            summary="CPU 부하가 평균 {0}%인데도 동작 클럭이 정격의 {1}배에 머물렀습니다.".format(
                load, ratio
            ),
            root_cause=(
                "과열 또는 전원 공급 제한으로 CPU가 스스로 클럭을 낮추고 있습니다. "
                "부품 성능은 그대로지만 실제로 쓰이지 못하는 상태입니다."
            ),
            recommended_action=ActionType.FIX,
            action_detail=(
                "쿨러 먼지와 서멀 그리스 상태를 점검하고 케이스 흡·배기를 확인하세요. "
                "노트북이라면 배터리 모드에서의 전력 제한일 수 있으니 충전기를 연결한 뒤 다시 측정하세요. "
                "청소와 설정으로 회복되면 부품 교체는 필요하지 않습니다."
            ),
            evidence=evidence,
            confidence=0.65,
        )
