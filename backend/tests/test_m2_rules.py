"""M2 telemetry 기반 진단 규칙 테스트 (M4).

합성 스냅샷만 쓴다. 실제 Windows 기기 없이도 규칙 하나하나를 검증할 수 있어야
규칙을 마음 놓고 고칠 수 있고, 임계값 변경이 회귀로 잡힌다.

이 파일이 지키려는 규약은 두 가지다.

1. **근거가 없으면 침묵한다.** 섹션이 없거나 값이 결측이면 Finding을 만들지 않는다.
   "이상 없음"과 "확인하지 못함"은 다른 결론이다.
2. **더 싼 조치가 있으면 그것을 권한다.** 같은 증상이라도 설정으로 해결되는
   구간에서는 구매를 권하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.diagnosis import diagnose, registry
from app.schemas.diagnosis import ActionType, Axis, Severity
from app.schemas.telemetry import TelemetrySnapshot

# --- 합성 스냅샷 -------------------------------------------------------------

#: 아무 규칙도 걸리지 않는 정상 상태. 각 테스트는 여기서 한 항목만 어긋나게 한다.
HEALTHY_STORAGE: dict[str, Any] = {
    "system_drive": "C:",
    "volumes": [
        {"drive": "C:", "size_gb": 500.0, "free_gb": 250.0, "free_percent": 50.0, "is_system": True},
        {"drive": "D:", "size_gb": 2000.0, "free_gb": 100.0, "free_percent": 5.0, "is_system": False},
    ],
    "disks": [
        {
            "index": 0,
            "model": "Samsung SSD 990 PRO",
            "size_gb": 500.0,
            "smart_supported": True,
            "predict_failure": False,
            "reallocated_sectors": 0,
            "pending_sectors": 0,
            "uncorrectable_sectors": 0,
            "power_on_hours": 1200,
            "host_writes_tb": 8.0,
            "wear_percent": 3,
        }
    ],
}

HEALTHY_RELIABILITY: dict[str, Any] = {
    "window_days": 30,
    "log_covers_window": True,
    "events": [],
    "totals": {
        "whea_corrected": 0,
        "whea_fatal": 0,
        "unexpected_shutdown": 0,
        "bugcheck": 0,
        "disk_error": 0,
        "filesystem_error": 0,
    },
}

HEALTHY_PERFORMANCE: dict[str, Any] = {
    "sampling": {"count": 3, "interval_ms": 1000},
    "cpu": {
        "usage_percent": {"avg": 12.0, "max": 20.0, "min": 5.0, "samples": [20.0, 5.0, 11.0]},
        "privileged_percent": {"avg": 1.0, "max": 2.0, "min": 0.0, "samples": [2.0, 0.0, 1.0]},
        "clock": {"current_mhz": 3600, "max_mhz": 3600, "ratio": 1.0},
    },
    "memory": {
        "available_mb": {"avg": 12000.0, "max": 12500.0, "min": 11800.0, "samples": []},
        "committed_percent": {"avg": 45.0, "max": 47.0, "min": 44.0, "samples": []},
        "pages_per_sec": {"avg": 20.0, "max": 30.0, "min": 10.0, "samples": []},
    },
    "disk": {
        "queue_length": {"avg": 0.0, "max": 0.1, "min": 0.0, "samples": []},
        "idle_percent": {"avg": 96.0, "max": 99.0, "min": 90.0, "samples": []},
    },
    "top_processes": [{"name": "explorer", "cpu_percent": 3.0, "memory_mb": 110.0}],
    "power_plan": {"name": "균형 조정", "scheme": "balanced", "is_power_saver": False},
    "thermal": {"available": False, "max_c": None, "zones_c": []},
}


def make_snapshot(
    storage_health: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    status: str = "ok",
) -> TelemetrySnapshot:
    """M2 섹션만 담은 스냅샷. hardware를 비워 M1 규칙의 간섭을 없앤다."""
    sections = {
        "hardware": {"status": "ok", "milestone": "M1", "data": {}},
        "storage_health": {
            "status": status,
            "milestone": "M2",
            "data": HEALTHY_STORAGE if storage_health is None else storage_health,
        },
        "reliability": {
            "status": status,
            "milestone": "M2",
            "data": HEALTHY_RELIABILITY if reliability is None else reliability,
        },
        "performance": {
            "status": status,
            "milestone": "M2",
            "data": HEALTHY_PERFORMANCE if performance is None else performance,
        },
    }
    return TelemetrySnapshot.model_validate(
        {
            "schema_version": "1.1.0",
            "snapshot_id": "test-m2",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scan_mode": "actual",
            "agent": {"version": "0.1.0", "os": "Windows"},
            "sections": sections,
        }
    )


def merged(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """fixture 한 항목만 바꾼 사본."""
    return {**base, **overrides}


def find(result, rule_id: str):
    return next((f for f in result.findings if f.rule_id == rule_id), None)


# --- 규약: 근거가 없으면 침묵한다 ---------------------------------------------


def test_healthy_m2_snapshot_produces_no_findings():
    result = diagnose(make_snapshot())
    assert result.findings == []
    assert result.decision.action is ActionType.KEEP


def test_rules_stay_silent_without_their_section():
    """섹션이 아예 없으면 M2 규칙은 하나도 돌지 않는다."""
    snapshot = TelemetrySnapshot.model_validate(
        {
            "schema_version": "1.1.0",
            "snapshot_id": "no-m2",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scan_mode": "actual",
            "agent": {"version": "0.1.0", "os": "Windows"},
            "sections": {"hardware": {"status": "ok", "data": {}}},
        }
    )
    result = diagnose(snapshot)
    assert result.findings == []
    # 못 본 것이 "이상 없음"으로 둔갑하지 않았는지는 coverage로 확인한다
    assert "storage_health" not in result.coverage


def test_rules_stay_silent_when_section_failed():
    """수집 실패(error) 섹션의 데이터는 판정 근거가 될 수 없다."""
    broken = merged(HEALTHY_STORAGE, volumes=[
        {"drive": "C:", "size_gb": 500.0, "free_gb": 2.0, "free_percent": 0.4, "is_system": True}
    ])
    result = diagnose(make_snapshot(storage_health=broken, status="error"))
    assert result.findings == []


@pytest.mark.parametrize(
    "storage_health",
    [
        {},
        {"volumes": [], "disks": []},
        # SMART 미지원 디스크: 권한이 없어 값이 전부 결측인 상태
        {
            "volumes": [{"drive": "C:", "is_system": True}],
            "disks": [{"index": 0, "model": "WDC", "smart_supported": False,
                       "predict_failure": None, "reallocated_sectors": None,
                       "pending_sectors": None, "wear_percent": None}],
        },
    ],
)
def test_missing_storage_values_produce_no_findings(storage_health):
    """결측을 0으로 읽어 '정상'이라고 말하지 않는다."""
    result = diagnose(make_snapshot(storage_health=storage_health))
    assert [f for f in result.findings if f.rule_id.startswith("ST-")] == []


def test_missing_performance_values_produce_no_findings():
    result = diagnose(make_snapshot(performance={"cpu": {}, "memory": {}, "power_plan": {}}))
    assert [f for f in result.findings if f.rule_id.startswith("PF-")] == []


# --- Storage 규칙 -------------------------------------------------------------


def test_low_system_volume_space_recommends_cleanup_not_purchase():
    """정리로 해결되는 문제에 새 디스크를 권하지 않는다."""
    storage = merged(HEALTHY_STORAGE, volumes=[
        {"drive": "C:", "size_gb": 500.0, "free_gb": 12.0, "free_percent": 2.4, "is_system": True}
    ])
    finding = find(diagnose(make_snapshot(storage_health=storage)), "ST-SPACE-001")
    assert finding is not None
    assert finding.recommended_action is ActionType.FIX
    assert finding.severity is Severity.HIGH
    assert finding.evidence


def test_large_disk_with_low_percentage_but_ample_space_is_not_flagged():
    """2TB의 8%(=160GB)는 부족하지 않다. 비율만 보면 오탐이 난다."""
    storage = merged(HEALTHY_STORAGE, volumes=[
        {"drive": "C:", "size_gb": 2000.0, "free_gb": 160.0, "free_percent": 8.0, "is_system": True}
    ])
    assert find(diagnose(make_snapshot(storage_health=storage)), "ST-SPACE-001") is None


def test_non_system_volume_shortage_is_ignored():
    """D 드라이브가 꽉 찬 것은 시스템 성능 문제가 아니다."""
    assert find(diagnose(make_snapshot()), "ST-SPACE-001") is None


def test_predicted_failure_is_critical_purchase():
    storage = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], predict_failure=True, predict_failure_reason=5)
    ])
    finding = find(diagnose(make_snapshot(storage_health=storage)), "ST-SMART-002")
    assert finding is not None
    assert finding.severity is Severity.CRITICAL
    assert finding.recommended_action is ActionType.PURCHASE


def test_pending_sector_raises_severity_over_reallocated():
    """대기 섹터는 한 개만 있어도 재할당 섹터보다 급하다."""
    few_reallocated = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], reallocated_sectors=2, pending_sectors=0)
    ])
    one_pending = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], reallocated_sectors=2, pending_sectors=1)
    ])

    mild = find(diagnose(make_snapshot(storage_health=few_reallocated)), "ST-SMART-001")
    urgent = find(diagnose(make_snapshot(storage_health=one_pending)), "ST-SMART-001")

    assert mild.severity is Severity.MEDIUM
    assert mild.recommended_action is ActionType.FIX
    assert urgent.severity is Severity.HIGH
    assert urgent.recommended_action is ActionType.PURCHASE


def test_moderate_wear_advises_planning_not_buying():
    """보증 수명은 고장 시점이 아니다. 70%대에서 구매를 권하면 과잉이다."""
    storage = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], wear_percent=75)
    ])
    finding = find(diagnose(make_snapshot(storage_health=storage)), "ST-WEAR-001")
    assert finding.recommended_action is ActionType.KEEP
    assert finding.severity is Severity.MEDIUM


def test_severe_wear_recommends_purchase():
    storage = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], wear_percent=95)
    ])
    finding = find(diagnose(make_snapshot(storage_health=storage)), "ST-WEAR-001")
    assert finding.recommended_action is ActionType.PURCHASE
    assert finding.severity is Severity.HIGH


# --- Reliability 규칙 ---------------------------------------------------------


def _totals(**counts: int) -> dict[str, Any]:
    totals = dict(HEALTHY_RELIABILITY["totals"])
    totals.update(counts)
    return merged(HEALTHY_RELIABILITY, totals=totals)


def test_whea_fatal_is_critical():
    finding = find(diagnose(make_snapshot(reliability=_totals(whea_fatal=1))), "RL-WHEA-002")
    assert finding.severity is Severity.CRITICAL
    assert finding.recommended_action is ActionType.PURCHASE
    assert finding.axis is Axis.HARDWARE


def test_few_corrected_whea_errors_stay_silent():
    """소수의 정정 오류는 정상 동작 범위다."""
    assert find(diagnose(make_snapshot(reliability=_totals(whea_corrected=2))), "RL-WHEA-001") is None


def test_moderate_whea_accumulation_tries_settings_first():
    """XMP 해제/재장착으로 사라지는 경우가 많다. 먼저 그쪽을 권한다."""
    finding = find(diagnose(make_snapshot(reliability=_totals(whea_corrected=8))), "RL-WHEA-001")
    assert finding.recommended_action is ActionType.FIX
    assert finding.severity is Severity.MEDIUM


def test_heavy_whea_accumulation_recommends_replacement():
    finding = find(diagnose(make_snapshot(reliability=_totals(whea_corrected=40))), "RL-WHEA-001")
    assert finding.recommended_action is ActionType.PURCHASE
    assert finding.severity is Severity.HIGH


def test_truncated_event_log_lowers_confidence():
    """로그가 관측 구간을 못 덮으면 실제 건수는 더 많을 수 있다."""
    full = _totals(whea_corrected=8)
    truncated = merged(full, log_covers_window=False)
    assert (
        find(diagnose(make_snapshot(reliability=truncated)), "RL-WHEA-001").confidence
        < find(diagnose(make_snapshot(reliability=full)), "RL-WHEA-001").confidence
    )


def test_single_crash_is_not_a_finding():
    """정전이나 강제 종료 한 번을 결함으로 보지 않는다."""
    assert find(diagnose(make_snapshot(reliability=_totals(unexpected_shutdown=1))), "RL-CRASH-001") is None


def test_repeated_crashes_ask_for_diagnosis_not_purchase():
    """원인 부품을 특정하지 못한 상태에서 구매를 권하는 것은 조언이 아니다."""
    reliability = _totals(unexpected_shutdown=2, bugcheck=2)
    finding = find(diagnose(make_snapshot(reliability=reliability)), "RL-CRASH-001")
    assert finding.recommended_action is ActionType.FIX
    assert finding.severity is Severity.HIGH


def test_few_disk_errors_suggest_checking_connection():
    finding = find(diagnose(make_snapshot(reliability=_totals(disk_error=2))), "RL-DISK-001")
    assert finding.recommended_action is ActionType.FIX


def test_many_disk_errors_recommend_replacement():
    finding = find(diagnose(make_snapshot(reliability=_totals(disk_error=15))), "RL-DISK-001")
    assert finding.recommended_action is ActionType.PURCHASE
    assert finding.severity is Severity.HIGH


# --- Performance 규칙 ---------------------------------------------------------


def test_memory_pressure_requires_two_signals():
    """커밋 비율만 높은 것은 예약일 뿐이라 판정하지 않는다."""
    committed_only = merged(
        HEALTHY_PERFORMANCE,
        memory={
            "available_mb": {"avg": 6000.0, "max": 6200.0, "min": 5800.0, "samples": []},
            "committed_percent": {"avg": 93.0, "max": 95.0, "min": 91.0, "samples": []},
            "pages_per_sec": {"avg": 30.0, "max": 40.0, "min": 20.0, "samples": []},
        },
    )
    assert find(diagnose(make_snapshot(performance=committed_only)), "PF-MEM-001") is None


def test_memory_pressure_detected_when_both_signals_present():
    starved = merged(
        HEALTHY_PERFORMANCE,
        memory={
            "available_mb": {"avg": 700.0, "max": 900.0, "min": 500.0, "samples": []},
            "committed_percent": {"avg": 96.0, "max": 98.0, "min": 94.0, "samples": []},
            "pages_per_sec": {"avg": 2400.0, "max": 3000.0, "min": 1800.0, "samples": []},
        },
    )
    finding = find(diagnose(make_snapshot(performance=starved)), "PF-MEM-001")
    assert finding.recommended_action is ActionType.PURCHASE
    assert finding.severity is Severity.HIGH


def test_power_saver_plan_is_a_free_fix():
    performance = merged(
        HEALTHY_PERFORMANCE,
        power_plan={"name": "절전", "scheme": "power_saver", "is_power_saver": True},
    )
    finding = find(diagnose(make_snapshot(performance=performance)), "PF-POWER-001")
    assert finding.recommended_action is ActionType.FIX
    assert finding.axis is Axis.SOFTWARE


def test_cpu_spike_is_not_sustained_load():
    """최대만 높고 최소가 낮으면 스파이크다. 이걸로 판정하면 오진이 난다."""
    spiky = merged(
        HEALTHY_PERFORMANCE,
        cpu={
            "usage_percent": {"avg": 72.0, "max": 99.0, "min": 8.0, "samples": [99.0, 8.0, 99.0]},
            "privileged_percent": {"avg": 3.0, "max": 5.0, "min": 1.0, "samples": []},
            "clock": {"current_mhz": 3600, "max_mhz": 3600, "ratio": 1.0},
        },
    )
    assert find(diagnose(make_snapshot(performance=spiky)), "PF-CPU-001") is None


def test_sustained_cpu_load_names_the_process_and_recommends_fix():
    busy = merged(
        HEALTHY_PERFORMANCE,
        cpu={
            "usage_percent": {"avg": 88.0, "max": 95.0, "min": 80.0, "samples": [95.0, 80.0, 89.0]},
            "privileged_percent": {"avg": 4.0, "max": 6.0, "min": 2.0, "samples": []},
            "clock": {"current_mhz": 3600, "max_mhz": 3600, "ratio": 1.0},
        },
        top_processes=[{"name": "xmrig", "cpu_percent": 380.0, "memory_mb": 120.0}],
    )
    finding = find(diagnose(make_snapshot(performance=busy)), "PF-CPU-001")
    assert finding.recommended_action is ActionType.FIX
    assert "xmrig" in finding.summary
    # 짧은 관측이라는 한계를 확신도에 반영한다
    assert finding.confidence <= 0.7


def test_low_clock_without_load_is_normal_power_saving():
    idle = merged(
        HEALTHY_PERFORMANCE,
        cpu={
            "usage_percent": {"avg": 4.0, "max": 8.0, "min": 1.0, "samples": []},
            "privileged_percent": {"avg": 1.0, "max": 2.0, "min": 0.0, "samples": []},
            "clock": {"current_mhz": 800, "max_mhz": 3600, "ratio": 0.22},
        },
    )
    assert find(diagnose(make_snapshot(performance=idle)), "PF-THROTTLE-001") is None


def test_throttling_under_load_is_detected():
    throttled = merged(
        HEALTHY_PERFORMANCE,
        cpu={
            "usage_percent": {"avg": 85.0, "max": 92.0, "min": 78.0, "samples": []},
            "privileged_percent": {"avg": 5.0, "max": 8.0, "min": 3.0, "samples": []},
            "clock": {"current_mhz": 1400, "max_mhz": 3600, "ratio": 0.39},
        },
    )
    finding = find(diagnose(make_snapshot(performance=throttled)), "PF-THROTTLE-001")
    assert finding.recommended_action is ActionType.FIX
    assert finding.severity is Severity.MEDIUM


def test_throttling_with_high_temperature_is_more_severe():
    hot = merged(
        HEALTHY_PERFORMANCE,
        cpu={
            "usage_percent": {"avg": 85.0, "max": 92.0, "min": 78.0, "samples": []},
            "privileged_percent": {"avg": 5.0, "max": 8.0, "min": 3.0, "samples": []},
            "clock": {"current_mhz": 1400, "max_mhz": 3600, "ratio": 0.39},
        },
        thermal={"available": True, "max_c": 96.0, "zones_c": [96.0]},
    )
    finding = find(diagnose(make_snapshot(performance=hot)), "PF-THROTTLE-001")
    assert finding.severity is Severity.HIGH
    assert len(finding.evidence) == 2


# --- M2가 M1 규칙의 정확도를 올리는 지점 ---------------------------------------


def _with_hardware(hardware: dict[str, Any], storage_health: dict[str, Any]):
    snapshot = make_snapshot(storage_health=storage_health)
    snapshot.sections["hardware"].data = hardware
    return snapshot


#: HDD가 0번, OS가 설치된 NVMe가 1번인 흔한 구성.
_MIXED_INVENTORY = {
    "storage": [
        {"model": "ST2000DM008", "size_gb": 2000.0, "media_type": "HDD", "interface": "IDE"},
        {"model": "Samsung SSD 990 PRO", "size_gb": 500.0, "media_type": "SSD", "interface": "SCSI"},
    ]
}


def test_data_hdd_is_not_mistaken_for_the_system_drive():
    """M2 이전에는 Index 0을 시스템 디스크로 가정해 이 구성에서 오진이 났다."""
    storage = merged(HEALTHY_STORAGE, disks=[
        {"index": 0, "model": "ST2000DM008", "is_system": False, "smart_supported": True,
         "predict_failure": False, "reallocated_sectors": 0, "pending_sectors": 0, "wear_percent": 0},
        {"index": 1, "model": "Samsung SSD 990 PRO", "is_system": True, "smart_supported": True,
         "predict_failure": False, "reallocated_sectors": 0, "pending_sectors": 0, "wear_percent": 3},
    ])
    result = diagnose(_with_hardware(_MIXED_INVENTORY, storage))
    assert find(result, "HW-DISK-001") is None


def test_system_hdd_is_still_detected():
    storage = merged(HEALTHY_STORAGE, disks=[
        {"index": 0, "model": "ST2000DM008", "is_system": True, "smart_supported": True,
         "predict_failure": False, "reallocated_sectors": 0, "pending_sectors": 0, "wear_percent": 0},
    ])
    finding = find(diagnose(_with_hardware(_MIXED_INVENTORY, storage)), "HW-DISK-001")
    assert finding is not None
    assert finding.confidence == 0.85


def test_guessing_the_system_disk_lowers_confidence():
    """storage_health가 없으면 Index 0 추정으로 떨어진다. 확신도로 그 사실을 드러낸다."""
    snapshot = TelemetrySnapshot.model_validate(
        {
            "schema_version": "1.1.0",
            "snapshot_id": "no-health",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scan_mode": "actual",
            "agent": {"version": "0.1.0", "os": "Windows"},
            "sections": {"hardware": {"status": "ok", "data": _MIXED_INVENTORY}},
        }
    )
    finding = find(diagnose(snapshot), "HW-DISK-001")
    assert finding is not None
    assert finding.confidence == 0.5


# --- 판정 종합 ---------------------------------------------------------------


def test_cheaper_action_wins_when_only_software_problems_exist():
    """소프트웨어로 해결 가능한 문제만 있으면 구매 권고가 나오면 안 된다."""
    performance = merged(
        HEALTHY_PERFORMANCE,
        power_plan={"name": "절전", "scheme": "power_saver", "is_power_saver": True},
    )
    storage = merged(HEALTHY_STORAGE, volumes=[
        {"drive": "C:", "size_gb": 500.0, "free_gb": 20.0, "free_percent": 4.0, "is_system": True}
    ])
    result = diagnose(make_snapshot(storage_health=storage, performance=performance))
    assert result.decision.action is ActionType.FIX
    assert {"PF-POWER-001", "ST-SPACE-001"} <= set(result.decision.driven_by)


def test_hardware_failure_overrides_software_fixes():
    storage = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], predict_failure=True)
    ])
    performance = merged(
        HEALTHY_PERFORMANCE,
        power_plan={"name": "절전", "scheme": "power_saver", "is_power_saver": True},
    )
    result = diagnose(make_snapshot(storage_health=storage, performance=performance))
    assert result.decision.action is ActionType.PURCHASE
    assert result.findings[0].rule_id == "ST-SMART-002"
    # 구매 판정이 나와도 무료 조치 항목은 사라지지 않는다
    assert find(result, "PF-POWER-001") is not None


def test_every_m2_rule_declares_its_section():
    """requires를 빠뜨리면 없는 데이터로 판정하게 된다. 구조적으로 막는다."""
    m2_sections = {"storage_health", "reliability", "performance"}
    for rule_id, cls in registry().items():
        if rule_id.startswith(("ST-", "RL-", "PF-")):
            assert set(cls.requires) & m2_sections, rule_id


def test_all_findings_carry_evidence_and_action():
    """근거 없는 결론은 만들지 않는다."""
    storage = merged(HEALTHY_STORAGE, disks=[
        merged(HEALTHY_STORAGE["disks"][0], predict_failure=True, reallocated_sectors=30,
               pending_sectors=4, wear_percent=95)
    ])
    result = diagnose(make_snapshot(storage_health=storage, reliability=_totals(whea_fatal=2)))
    assert len(result.findings) >= 4
    for finding in result.findings:
        assert finding.evidence, finding.rule_id
        assert finding.action_detail, finding.rule_id
        assert finding.root_cause, finding.rule_id
