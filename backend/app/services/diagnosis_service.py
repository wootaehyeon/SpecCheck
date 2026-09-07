"""Application service for UI-facing diagnosis responses."""

from app.diagnosis import diagnose
from app.diagnosis.adapter import to_ui_diagnosis
from app.diagnosis.explainer import explain_for_ui_bundle
from app.diagnosis.recommendations import build_recommendations
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import UiDiagnosis


def diagnose_for_ui(snapshot: TelemetrySnapshot) -> UiDiagnosis:
    result = diagnose(snapshot)
    recommendations = build_recommendations(snapshot, result)
    ai, recommendations = explain_for_ui_bundle(result, recommendations)
    return to_ui_diagnosis(snapshot, result, ai, recommendations)
