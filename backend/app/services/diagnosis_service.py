"""Application service for UI-facing diagnosis responses."""

import hashlib
import json
import threading

from app.diagnosis import diagnose
from app.diagnosis.adapter import to_ui_diagnosis
from app.diagnosis.explainer import explain_for_ui_bundle
from app.diagnosis.recommendations import build_recommendations
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import UiDiagnosis
from app.services import scan_service
from app.services.component_catalog import load_catalog
from app.services.purchase_market import offers_state, enrich

# Bump when the persisted UI contract or diagnosis interpretation changes.
DIAGNOSIS_REVISION = "ui-1.2-catalog-market-v2"
_LOCKS = [threading.Lock() for _ in range(32)]


def diagnose_for_ui(snapshot: TelemetrySnapshot, *, refresh: bool = False) -> UiDiagnosis:
    canonical = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    catalog, catalog_revision = load_catalog()
    result = diagnose(snapshot)
    recommendations = build_recommendations(snapshot, result, catalog)
    candidate_ids = {part.key for recommendation in recommendations for candidate in recommendation.candidates for part in candidate.parts}
    market, market_revision = offers_state([p for p in catalog if p['id'] in candidate_ids])
    input_key = hashlib.sha256((DIAGNOSIS_REVISION + catalog_revision + market_revision + canonical).encode("utf-8")).hexdigest()
    lock = _LOCKS[int(hashlib.sha256(snapshot.snapshot_id.encode("utf-8")).hexdigest(), 16) % len(_LOCKS)]
    # SQLite survives restarts; the lock coalesces concurrent requests in this server.
    with lock:
        if not refresh:
            stored = scan_service.get_ui_diagnosis(snapshot.snapshot_id, input_key)
            if stored is not None:
                return stored
        recommendations = enrich(recommendations, market)
        ai, recommendations = explain_for_ui_bundle(result, recommendations)
        diagnosis = to_ui_diagnosis(snapshot, result, ai, recommendations)
        scan_service.save_ui_diagnosis(snapshot.snapshot_id, input_key, diagnosis)
        return diagnosis
