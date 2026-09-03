"""Application service for UI-facing diagnosis responses."""

from app.diagnosis import diagnose
from app.diagnosis.adapter import to_ui_diagnosis
from app.diagnosis.explainer import explain_for_ui
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import UiDiagnosis


def diagnose_for_ui(snapshot: TelemetrySnapshot) -> UiDiagnosis:
    result = diagnose(snapshot)
    return to_ui_diagnosis(snapshot, result, explain_for_ui(result))
