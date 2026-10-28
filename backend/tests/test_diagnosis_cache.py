"""Persistent UI results, invalidation, and concurrent generation."""

import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.schemas.telemetry import TelemetrySnapshot
from app.services import diagnosis_service, scan_service


@pytest.fixture
def cached_scan(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "snapshot_db", tmp_path / "snapshots.db")
    snapshot = TelemetrySnapshot.model_validate({
        "schema_version": "1.1.0", "snapshot_id": "cache-test",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scan_mode": "actual", "device_id": "cache-device",
        "agent": {"version": "0.1.0", "os": "Windows"},
        "sections": {"hardware": {"status": "ok", "data": {}}},
    })
    calls = []

    def explain(result, recommendations):
        calls.append(result.snapshot_id)
        return {
            "provider": "template", "model": "test", "status": "fallback",
            "overview": "Saved explanation", "actionPlan": ["Check again later"],
        }, recommendations

    monkeypatch.setattr(diagnosis_service, "explain_for_ui_bundle", explain)
    return snapshot, calls


def test_repeat_reads_and_fallback_results_are_stable(cached_scan):
    snapshot, calls = cached_scan
    first = diagnosis_service.diagnose_for_ui(snapshot)
    second = diagnosis_service.diagnose_for_ui(snapshot)
    assert first.model_dump() == second.model_dump()
    assert calls == [snapshot.snapshot_id]


def test_catalog_changes_invalidate_saved_diagnosis(cached_scan, monkeypatch):
    snapshot, calls = cached_scan
    products, revision = diagnosis_service.load_catalog()
    diagnosis_service.diagnose_for_ui(snapshot)
    monkeypatch.setattr(diagnosis_service, "load_catalog", lambda: (products, revision + "updated"))
    diagnosis_service.diagnose_for_ui(snapshot)
    diagnosis_service.diagnose_for_ui(snapshot)
    assert len(calls) == 2


def test_purchase_changes_invalidate_saved_diagnosis(cached_scan, monkeypatch):
    snapshot, calls = cached_scan
    state, revision = diagnosis_service.offers_state()
    diagnosis_service.diagnose_for_ui(snapshot)
    monkeypatch.setattr(diagnosis_service, "offers_state", lambda products=None: (state, revision + "updated"))
    diagnosis_service.diagnose_for_ui(snapshot)
    diagnosis_service.diagnose_for_ui(snapshot)
    assert len(calls) == 2


def test_latest_api_reuses_result_and_post_can_refresh(cached_scan):
    snapshot, calls = cached_scan
    scan_service.save_snapshot(snapshot)
    with TestClient(app) as client:
        first = client.get("/api/scans/latest")
        second = client.get("/api/scans/latest")
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert len(calls) == 1
        refreshed = client.post("/api/scans", json={"refresh": True})
        assert refreshed.status_code == 200
        assert len(calls) == 2
        assert client.get("/api/scans/latest").json() == refreshed.json()
        assert len(calls) == 2


def test_result_survives_a_new_python_process(cached_scan):
    snapshot, _ = cached_scan
    scan_service.save_snapshot(snapshot)
    original = diagnosis_service.diagnose_for_ui(snapshot)
    script = """
from app.services import scan_service, diagnosis_service
def forbidden(*args):
    raise AssertionError('Cached read must not call Gemma')
diagnosis_service.explain_for_ui_bundle = forbidden
result = diagnosis_service.diagnose_for_ui(scan_service.get_snapshot('cache-test'))
print(result.model_dump_json(by_alias=True))
"""
    environment = {**os.environ, "SNAPSHOT_DB": str(get_settings().snapshot_db)}
    process = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True, check=True)
    assert original == type(original).model_validate_json(process.stdout)


def test_refresh_content_and_revision_each_invalidate(cached_scan, monkeypatch):
    snapshot, calls = cached_scan
    diagnosis_service.diagnose_for_ui(snapshot)
    diagnosis_service.diagnose_for_ui(snapshot, refresh=True)
    changed = snapshot.model_copy(update={"device_id": "changed-device"})
    diagnosis_service.diagnose_for_ui(changed)
    monkeypatch.setattr(diagnosis_service, "DIAGNOSIS_REVISION", "next-version")
    diagnosis_service.diagnose_for_ui(changed)
    assert len(calls) == 4


def test_concurrent_reads_generate_once(cached_scan):
    snapshot, calls = cached_scan
    barrier = threading.Barrier(4)

    def read():
        barrier.wait(timeout=5)
        return diagnosis_service.diagnose_for_ui(snapshot)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: read(), range(4)))
    assert len(calls) == 1
    assert all(result == results[0] for result in results)


def test_failed_refresh_keeps_the_previous_result(cached_scan, monkeypatch):
    snapshot, _ = cached_scan
    original = diagnosis_service.diagnose_for_ui(snapshot)

    def fail(*args):
        raise RuntimeError("generation failed")

    monkeypatch.setattr(diagnosis_service, "explain_for_ui_bundle", fail)
    with pytest.raises(RuntimeError, match="generation failed"):
        diagnosis_service.diagnose_for_ui(snapshot, refresh=True)
    assert diagnosis_service.diagnose_for_ui(snapshot) == original
