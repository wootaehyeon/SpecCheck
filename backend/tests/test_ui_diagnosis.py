"""Telemetry to diagnosis 1.1 adapter contract tests."""

from datetime import datetime, timezone

from app.diagnosis import diagnose
from app.diagnosis.adapter import score_findings, to_ui_diagnosis
from app.schemas.diagnosis import ActionType, Axis, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot


def make_snapshot(storage_status: str = "ok", storage_errors: list[str] | None = None):
    return TelemetrySnapshot.model_validate(
        {
            "schema_version": "1.1.0",
            "snapshot_id": "ui-contract-snapshot",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scan_mode": "actual",
            "device_id": "25264e6dc980abcdef",
            "agent": {"version": "0.1.0", "os": "Windows", "os_version": "10.0.26200"},
            "sections": {
                "hardware": {
                    "status": "ok",
                    "data": {
                        "os": {"caption": "Windows 11 Pro", "build": "26200"},
                        "cpu": [{"name": "Test CPU", "cores": 8, "threads": 16, "max_clock_mhz": 4200}],
                        "memory": {"total_gb": 4, "module_count": 1, "modules": []},
                        "gpu": [],
                        "storage": [],
                        "motherboard": {},
                    },
                },
                "storage_health": {
                    "status": storage_status,
                    "data": {"volumes": [], "disks": [], "collect_errors": storage_errors or []},
                },
                "reliability": {"status": "ok", "data": {"totals": {}}},
                "performance": {"status": "ok", "data": {}},
                "security": {"status": "planned", "milestone": "M6", "data": {}},
            },
        }
    )


def fallback_ai():
    return {
        "provider": "template",
        "model": "deterministic-ko-v1",
        "status": "fallback",
        "overview": "테스트 설명",
        "actionPlan": ["테스트 조치"],
    }


def test_risk_score_stays_inside_highest_severity_band():
    finding = Finding(
        rule_id="TEST-HIGH",
        title="테스트",
        axis=Axis.HARDWARE,
        severity=Severity.HIGH,
        summary="테스트",
        recommended_action=ActionType.FIX,
        confidence=0.9,
    )
    assert 70 <= score_findings([finding]) < 85


def test_adapter_preserves_action_decision_and_aliases():
    snapshot = make_snapshot()
    diagnosis = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai())
    payload = diagnosis.model_dump(by_alias=True, mode="json")

    assert payload["schemaVersion"] == "1.1.0"
    assert payload["machine"]["name"] == "25264e6dc980"
    assert payload["status"] == "complete"
    assert payload["decision"]["action"] == "purchase"
    assert payload["findings"][0]["recommendedAction"] == "purchase"
    assert payload["recommendations"] == [
        {
            "id": "memory-upgrade",
            "findingIds": ["HW-RAM-002"],
            "priority": "high",
            "category": "memory",
            "title": "메모리 16GB 이상 증설 검토",
            "description": "물리 메모리 부족의 근거로 물리 메모리 증설을 우선 검토하세요. 구매 전 메인보드의 DDR 세대와 빈 슬롯을 확인해야 합니다.",
            "searchQuery": "16GB PC 메모리",
            "searchUrl": "https://search.shopping.naver.com/search/all?query=16GB+PC+%EB%A9%94%EB%AA%A8%EB%A6%AC",
        }
    ]
    assert payload["sources"][-1]["status"] == "not_in_scope"


def test_permission_limited_section_is_not_reported_as_collected():
    snapshot = make_snapshot(
        storage_status="partial",
        storage_errors=["SMART 조회에는 관리자 권한이 필요합니다."],
    )
    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)
    storage = next(source for source in payload["sources"] if source["name"] == "storage")
    assert storage["status"] == "permission_required"
    assert storage["collectedAt"] is None
