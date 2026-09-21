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


def test_ollama_status_prefers_gemma4_when_both_models_are_installed(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_model", "gemma4:e2b")
    monkeypatch.setattr(settings, "llm_fallback_model", "gemma3:4b")
    monkeypatch.setattr(
        explainer,
        "_list_ollama_models",
        lambda *_: ["gemma3:4b", "gemma4:e2b"],
    )

    status = explainer.ollama_status()

    assert status["available"] is True
    assert status["installed"] is True
    assert status["model"] == "gemma4:e2b"
    assert status["usingFallback"] is False


def test_ollama_status_uses_legacy_model_until_gemma4_is_downloaded(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_model", "gemma4:e2b")
    monkeypatch.setattr(settings, "llm_fallback_model", "gemma3:4b")
    monkeypatch.setattr(explainer, "_list_ollama_models", lambda *_: ["gemma3:4b"])

    status = explainer.ollama_status()

    assert status["installed"] is True
    assert status["model"] == "gemma3:4b"
    assert status["fallbackModel"] == "gemma3:4b"
    assert status["usingFallback"] is True


def test_permission_limited_section_is_not_reported_as_collected():
    snapshot = make_snapshot(
        storage_status="partial",
        storage_errors=["SMART 조회에는 관리자 권한이 필요합니다."],
    )
    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)
    storage = next(source for source in payload["sources"] if source["name"] == "storage")
    assert storage["status"] == "permission_required"
    assert storage["collectedAt"] is None


def test_missing_sysmon_is_not_reported_as_a_collected_security_source():
    raw = make_snapshot().model_dump(mode="json")
    raw["sections"]["security"] = {
        "status": "partial",
        "milestone": "M5",
        "data": {"sysmon": {"status": "skipped", "reason": "sysmon_channel_unavailable"}},
    }
    snapshot = TelemetrySnapshot.model_validate(raw)

    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)
    sysmon = next(source for source in payload["sources"] if source["name"] == "sysmon")

    assert sysmon["status"] == "unavailable"
    assert sysmon["collectedAt"] is None
    assert [item["title"] for item in sysmon["requirements"]] == [
        "Sysmon 설치 및 Operational 로그 활성화",
        "관리자 권한으로 재검사",
    ]


def test_collected_sysmon_without_a_finding_is_described_as_checked():
    raw = make_snapshot().model_dump(mode="json")
    raw["sections"]["security"] = {
        "status": "ok",
        "data": {"sysmon": {"status": "ok", "events": []}},
    }
    snapshot = TelemetrySnapshot.model_validate(raw)

    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)

    assert payload["categories"]["security"]["summary"] == "보안 이벤트를 수집했지만 확정된 이상은 없습니다"


def test_pending_builtin_sysmon_feature_requires_a_restart():
    raw = make_snapshot().model_dump(mode="json")
    raw["sections"]["security"] = {
        "status": "partial",
        "milestone": "M5",
        "data": {"sysmon": {"status": "skipped", "reason": "sysmon_setup_restart_required"}},
    }
    snapshot = TelemetrySnapshot.model_validate(raw)

    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)
    sysmon = next(source for source in payload["sources"] if source["name"] == "sysmon")

    assert sysmon["requirements"] == [{
        "title": "Windows 다시 시작 필요",
        "detail": "내장 Sysmon 기능을 활성화했습니다. 재시작 후 다시 진단하면 이벤트 수집을 자동으로 완료합니다.",
    }]


def test_adapter_exposes_bounded_correlation_candidates_without_process_identifier():
    raw = make_snapshot().model_dump(mode="json")
    raw["sections"]["correlation"] = {
        "status": "ok",
        "milestone": "M6",
        "data": {
            "candidates": [{
                "id": "background_load",
                "rank": 1,
                "confidence": 0.65,
                "process_key": "a" * 64,
                "evidence": {
                    "cpu_percent": 95,
                    "event_ids": [1, 3, 22],
                    "window_seconds": 120,
                },
            }],
        },
    }
    snapshot = TelemetrySnapshot.model_validate(raw)

    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)

    candidate = payload["rootCauseCandidates"][0]
    assert candidate["id"] == "background_load"
    assert candidate["action"] == "fix"
    assert candidate["evidence"] == [
        "CPU 사용률 95%",
        "동일 프로세스의 프로세스 생성·네트워크 연결·DNS 조회 활동",
        "120초 시간 창에서 상관됨",
    ]
    assert "a" * 64 not in str(payload)


def test_adapter_exposes_anomaly_as_context_without_creating_a_finding():
    raw = make_snapshot().model_dump(mode="json")
    raw["sections"]["anomaly"] = {
        "status": "ok",
        "milestone": "M7",
        "data": {
            "method": "z_score",
            "required_baseline_samples": 3,
            "evaluated_metrics": 5,
            "signals": [{
                "metric": "performance.cpu.usage_percent",
                "z_score": 15.0,
                "value": 95.0,
                "baseline_mean": 20.0,
                "samples": 3,
            }],
        },
    }
    snapshot = TelemetrySnapshot.model_validate(raw)
    baseline = diagnose(snapshot)

    payload = to_ui_diagnosis(snapshot, baseline, fallback_ai()).model_dump(by_alias=True)

    analysis = payload["anomalyAnalysis"]
    assert analysis["status"] == "signal_detected"
    assert analysis["signals"] == [{
        "metric": "performance.cpu.usage_percent",
        "label": "CPU 사용률",
        "direction": "above_baseline",
        "zScore": 15.0,
        "value": 95.0,
        "baselineMean": 20.0,
        "samples": 3,
    }]
    assert all(item["code"] != "M7-ANOMALY" for item in payload["findings"])


def test_adapter_exposes_trajectory_as_an_approximate_context_only():
    raw = make_snapshot().model_dump(mode="json")
    raw["sections"]["trajectory"] = {
        "status": "ok",
        "milestone": "M8",
        "data": {
            "method": "linear_regression",
            "required_samples": 3,
            "minimum_span_days": 1,
            "trends": [{
                "metric": "storage.free_percent",
                "samples": 7,
                "slope_per_day": -0.9,
                "threshold": 10,
                "threshold_at": "2026-12-18T00:00:00+00:00",
                "threshold_at_interval_approx": [
                    "2026-12-02T00:00:00+00:00",
                    "2027-01-10T00:00:00+00:00",
                ],
            }],
        },
    }
    snapshot = TelemetrySnapshot.model_validate(raw)

    payload = to_ui_diagnosis(snapshot, diagnose(snapshot), fallback_ai()).model_dump(by_alias=True)

    analysis = payload["trajectoryAnalysis"]
    assert analysis["status"] == "ready"
    assert analysis["trends"] == [{
        "metric": "storage.free_percent",
        "label": "시스템 드라이브 여유 공간",
        "direction": "worsening",
        "samples": 7,
        "slopePerDay": -0.9,
        "threshold": 10.0,
        "thresholdAt": "2026-12-18T00:00:00+00:00",
        "thresholdRange": ["2026-12-02T00:00:00+00:00", "2027-01-10T00:00:00+00:00"],
    }]
    assert "고장 시점" in analysis["limitation"]
