"""Telemetry to diagnosis 1.2 adapter contract tests."""

from datetime import datetime, timezone

from app.diagnosis import diagnose
from app.diagnosis.adapter import score_findings, to_ui_diagnosis
from app.diagnosis import explainer
from app.diagnosis.explainer import explain_for_ui_bundle
from app.diagnosis.recommendations import build_recommendations
from app.core.config import get_settings
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
                        "memory": {
                            "total_gb": 4,
                            "module_count": 1,
                            "slot_count": 2,
                            "empty_slot_count": 1,
                            "modules": [{"capacity_gb": 4, "rated_speed_mhz": 3200}],
                        },
                        "gpu": [],
                        "storage": [],
                        "motherboard": {"manufacturer": "Test", "product": "B450 Board"},
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

    assert payload["schemaVersion"] == "1.2.0"
    assert payload["machine"]["name"] == "25264e6dc980"
    assert payload["status"] == "complete"
    assert payload["decision"]["action"] == "purchase"
    assert payload["findings"][0]["recommendedAction"] == "purchase"
    recommendation = payload["recommendations"][0]
    assert recommendation["findingIds"] == ["HW-RAM-002"]
    assert recommendation["title"] == "호환 메모리 증설 제안"
    assert [candidate["strategy"] for candidate in recommendation["candidates"]] == ["minimal"]
    minimal = recommendation["candidates"][0]
    assert minimal["recommended"] is True
    assert minimal["compatibilityStatus"] == "passed"
    assert minimal["parts"][0]["name"] == "Kingston FURY Beast DDR4 32GB 3200MT/s Kit"
    assert minimal["parts"][0]["sourceLabel"] == "Kingston FURY Beast DDR4 제품 정보"
    assert recommendation["aiInsight"]["status"] == "fallback"
    assert payload["sources"][-1]["status"] == "not_in_scope"


def test_local_gemma_only_enriches_recommendation_explanation(monkeypatch):
    snapshot = make_snapshot()
    result = diagnose(snapshot)
    recommendations = build_recommendations(snapshot, result)
    original_parts = [part.name for part in recommendations[0].candidates[0].parts]
    original_score = recommendations[0].candidates[0].compatibility_score
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(explainer, "ollama_status", lambda: {
        "available": True, "model": settings.llm_model, "installed": True,
    })
    monkeypatch.setattr(explainer, "_ask_ollama_bundle_json", lambda *args, **kwargs: {
        "overview": "메모리 부족이 우선입니다.",
        "actionPlan": ["호환 메모리를 확인하세요."],
        "recommendations": [{
            "id": "memory-recommendation",
            "candidateId": "kingston-fury-beast-ddr4-32gb-3200",
            "rationale": "현재 플랫폼을 유지하는 최소 증설안이 비용과 작업 범위가 작습니다.",
            "cautions": ["장착 전 빈 슬롯을 다시 확인하세요."],
        }],
    })

    ai, enriched = explain_for_ui_bundle(result, recommendations)

    assert ai["provider"] == "ollama"
    assert enriched[0].ai_insight.status == "generated"
    assert enriched[0].ai_insight.provider == "ollama"
    assert [part.name for part in enriched[0].candidates[0].parts] == original_parts
    assert enriched[0].candidates[0].compatibility_score == original_score


def test_permission_limited_section_is_not_reported_as_collected():
    snapshot = make_snapshot(
        storage_status="partial",
        storage_errors=["SMART 조회에는 관리자 권한이 필요합니다."],
    )
    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)
    storage = next(source for source in payload["sources"] if source["name"] == "storage")
    assert storage["status"] == "permission_required"
    assert storage["collectedAt"] is None
