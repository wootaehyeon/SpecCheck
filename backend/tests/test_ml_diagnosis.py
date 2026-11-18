"""Inference separation, evidence integrity and model artifact contracts."""
import json

import pytest

from app.diagnosis import diagnose, registry
from app.diagnosis import ml
from app.diagnosis.ml_features import FEATURES
from app.schemas.telemetry import TelemetrySnapshot


def snapshot(sections):
    return TelemetrySnapshot.model_validate({
        "schema_version": "1.1.0", "snapshot_id": "ml-test", "scan_mode": "actual",
        "collected_at": "2026-11-18T00:00:00Z", "agent": {"version": "test", "os": "Windows"},
        "sections": {name: {"status": "ok", "data": data} for name, data in sections.items()},
    })


def test_live_inference_never_evaluates_legacy_rules(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Legacy rules must only run offline during training")
    for cls in registry().values():
        monkeypatch.setattr(cls, "evaluate", forbidden)
    result = diagnose(snapshot({"hardware": {"memory": {"total_gb": 4}}}))
    assert result.decision.action.value == "purchase"
    assert result.inference_method == "machine_learning"
    assert result.model_version == ml.model_version()
    assert result.training_label_source == "legacy_rule_weak_supervision"


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -10, "4"])
def test_unusable_measurements_abstain(value):
    assert not diagnose(snapshot({"hardware": {"memory": {"total_gb": value}}})).findings


def test_multiple_devices_and_failed_sections():
    data = snapshot({"storage_health": {"disks": [{"wear_percent": 0}, {"wear_percent": 95}]}})
    result = diagnose(data)
    assert result.findings[0].evidence[0].value["wear_percent"] == 95
    assert "95" in result.findings[0].evidence[0].detail
    data.sections["storage_health"].status = "error"
    assert not diagnose(data).findings


def test_no_training_example_measurements_leak_into_explanation():
    finding = diagnose(snapshot({"hardware": {"memory": {"total_gb": 3.25}}})).findings[0]
    assert finding.evidence[0].value["total_gb"] == 3.25
    assert "3.25" in finding.evidence[0].detail
    assert finding.model_score is not None


def test_missing_model_fails_instead_of_silent_rule_fallback(tmp_path, monkeypatch):
    ml.load_model.cache_clear()
    monkeypatch.setattr(ml, "MODEL_PATH", tmp_path / "absent.json")
    try:
        with pytest.raises(FileNotFoundError):
            diagnose(snapshot({}))
    finally:
        ml.load_model.cache_clear()


def test_model_and_report_cover_all_legacy_categories():
    artifact, _ = ml.load_model()
    assert set(artifact["models"]) == set(registry()) == set(FEATURES)
    report = json.loads(ml.MODEL_PATH.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert report["real_outcome_validation"] is False
    for result in report["models"].values():
        if result["validation_rows"]:
            assert result["teacher_agreement"] >= 0.98
            assert result["macro_f1"] >= 0.95


def test_historical_results_are_not_relabelled_as_ml():
    from app.schemas.diagnosis import DiagnosisResult
    payload = diagnose(snapshot({})).model_dump()
    for key in ("inference_method", "model_version", "training_label_source"):
        payload.pop(key)
    historical = DiagnosisResult.model_validate(payload)
    assert historical.inference_method == "legacy_rules"
    assert historical.model_version is None
