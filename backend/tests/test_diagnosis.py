"""진단 엔진 테스트.

규칙 하나하나의 판정보다, 엔진이 지켜야 할 규약을 검증한다.
- 데이터가 없으면 판정하지 않는다
- 소프트웨어로 고칠 수 있으면 구매를 권하지 않는다
- 이상이 없으면 유지(No-Purchase)가 기본값이다
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.diagnosis import diagnose, registry
from app.diagnosis.explainer import build_prompt, render_template
from app.schemas.diagnosis import ActionType, Axis, Severity
from app.schemas.telemetry import TelemetrySnapshot


def make_snapshot(hardware: dict | None = None, status: str = "ok", scan_mode: str = "actual"):
    sections = {
        "hardware": {"status": status, "milestone": "M1", "data": hardware or {}},
        "performance": {"status": "planned", "milestone": "M2"},
    }
    return TelemetrySnapshot.model_validate(
        {
            "schema_version": "1.0.0",
            "snapshot_id": "test-snapshot",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scan_mode": scan_mode,
            "agent": {"version": "0.1.0", "os": "Windows"},
            "sections": sections,
        }
    )


HEALTHY = {
    "memory": {
        "total_gb": 32.0,
        "module_count": 2,
        "modules": [{"rated_speed_mhz": 6000, "configured_speed_mhz": 6000, "slot": "DIMM0"}],
    },
    "storage": [{"model": "Samsung 990 PRO", "media_type": "SSD", "bus_type": "NVMe", "size_gb": 1000}],
    "gpu": [{"name": "NVIDIA GeForce RTX 4070", "driver_date": datetime.now(timezone.utc).isoformat()}],
    "motherboard": {"bios": {"version": "F5", "released_at": datetime.now(timezone.utc).isoformat()}},
}


def _stale(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# --- 엔진 규약 ---------------------------------------------------------------


def test_healthy_pc_results_in_keep():
    """이상이 없으면 구매하지 않는 것이 결론이다."""
    result = diagnose(make_snapshot(HEALTHY))
    assert result.findings == []
    assert result.decision.action is ActionType.KEEP


def test_rules_are_skipped_when_section_is_unusable():
    """수집 실패한 섹션으로는 아무것도 판정하지 않는다."""
    result = diagnose(make_snapshot({"memory": {"total_gb": 4.0}}, status="error"))
    assert result.findings == []
    assert result.coverage["hardware"] == "error"


def test_missing_fields_do_not_produce_findings():
    """필드가 비어 있으면 '문제 없음'이 아니라 '판정 불가'로 다룬다."""
    result = diagnose(make_snapshot({"memory": {}, "storage": [], "gpu": []}))
    assert result.findings == []


def test_estimated_scan_has_lower_confidence():
    actual = diagnose(make_snapshot(HEALTHY, scan_mode="actual"))
    estimated = diagnose(make_snapshot(HEALTHY, scan_mode="estimated"))
    assert estimated.confidence < actual.confidence


def test_planned_sections_do_not_reduce_confidence():
    """미구현 collector는 사용자 환경 문제가 아니므로 신뢰도에서 제외한다."""
    result = diagnose(make_snapshot(HEALTHY))
    assert result.confidence == 1.0


def test_rule_ids_are_unique_and_stable():
    ids = list(registry())
    assert len(ids) == len(set(ids))
    # 리포트/피드백이 rule_id로 규칙을 추적하므로 형식을 고정한다
    assert all("-" in rule_id for rule_id in ids)


# --- 개별 규칙 ---------------------------------------------------------------


def test_ram_speed_mismatch_recommends_fix_not_purchase():
    """XMP 미적용은 BIOS 설정 문제다. 램을 새로 사라고 하면 안 된다."""
    data = dict(HEALTHY)
    data["memory"] = {
        "total_gb": 32.0,
        "module_count": 2,
        "modules": [{"rated_speed_mhz": 6000, "configured_speed_mhz": 4800, "slot": "DIMM0"}],
    }
    result = diagnose(make_snapshot(data))
    finding = next(f for f in result.findings if f.rule_id == "HW-RAM-001")
    assert finding.recommended_action is ActionType.FIX
    assert finding.evidence
    assert result.decision.action is ActionType.FIX


def test_hdd_system_disk_recommends_purchase():
    data = dict(HEALTHY)
    data["storage"] = [{"model": "WDC WD10EZEX", "media_type": "HDD", "size_gb": 1000}]
    result = diagnose(make_snapshot(data))
    finding = next(f for f in result.findings if f.rule_id == "HW-DISK-001")
    assert finding.recommended_action is ActionType.PURCHASE
    assert finding.severity is Severity.HIGH


def test_low_memory_recommends_purchase():
    data = dict(HEALTHY)
    data["memory"] = {"total_gb": 4.0, "module_count": 1, "modules": []}
    result = diagnose(make_snapshot(data))
    assert any(f.rule_id == "HW-RAM-002" for f in result.findings)


def test_stale_gpu_driver_is_software_axis():
    data = dict(HEALTHY)
    data["gpu"] = [{"name": "RTX 3060", "driver_version": "471.11", "driver_date": _stale(900)}]
    result = diagnose(make_snapshot(data))
    finding = next(f for f in result.findings if f.rule_id == "SW-GPU-001")
    assert finding.axis is Axis.SOFTWARE
    assert finding.recommended_action is ActionType.FIX


def test_stale_bios_detected():
    data = dict(HEALTHY)
    data["motherboard"] = {"bios": {"version": "F2", "released_at": _stale(1500)}}
    result = diagnose(make_snapshot(data))
    assert any(f.rule_id == "SW-BIOS-001" for f in result.findings)


# --- 판정 종합 ---------------------------------------------------------------


def test_purchase_wins_over_fix_when_both_present():
    data = dict(HEALTHY)
    data["storage"] = [{"model": "WDC HDD", "media_type": "HDD", "size_gb": 1000}]
    data["gpu"] = [{"name": "RTX 3060", "driver_date": _stale(900)}]
    result = diagnose(make_snapshot(data))
    assert result.decision.action is ActionType.PURCHASE
    assert "HW-DISK-001" in result.decision.driven_by
    # 구매 판정이 나와도 소프트웨어 조치 항목은 사라지지 않는다
    assert any(f.recommended_action is ActionType.FIX for f in result.findings)


def test_findings_sorted_by_severity():
    data = dict(HEALTHY)
    data["storage"] = [{"model": "WDC HDD", "media_type": "HDD", "size_gb": 1000}]
    data["motherboard"] = {"bios": {"version": "F2", "released_at": _stale(1500)}}
    result = diagnose(make_snapshot(data))
    severities = [f.severity for f in result.findings]
    assert severities[0] is Severity.HIGH


# --- 설명 -------------------------------------------------------------------


def test_template_explanation_contains_decision():
    result = diagnose(make_snapshot(HEALTHY))
    text = render_template(result)
    assert "유지한다" in text


def test_prompt_only_contains_confirmed_findings():
    """LLM에는 telemetry 원본이 아니라 확정된 Finding만 넘긴다.

    모델이 스스로 진단을 지어내지 못하게 하는 구조적 장치이므로,
    Evidence의 원시 값(dict)이나 스냅샷 메타데이터는 프롬프트에 들어가면 안 된다.
    """
    data = dict(HEALTHY)
    data["storage"] = [{"model": "WDC WD10EZEX", "media_type": "HDD", "size_gb": 1000}]
    result = diagnose(make_snapshot(data))
    prompt = build_prompt(result)

    assert "시스템 드라이브가 HDD" in prompt
    for leaked in ("size_gb", "media_type", "schema_version", "snapshot_id"):
        assert leaked not in prompt


@pytest.mark.parametrize("action", list(ActionType))
def test_every_action_has_a_label(action):
    from app.diagnosis.explainer import _ACTION_LABEL

    assert action in _ACTION_LABEL
