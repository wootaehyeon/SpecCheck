import argparse
import json
from pathlib import Path
from uuid import uuid4

import pytest

from speccheck_agent import watch
from speccheck_agent.collectors.base import CollectorResult
from speccheck_agent.config import AgentConfig
from speccheck_agent.pipeline import SnapshotStore
from speccheck_agent.snapshot import build_snapshot


@pytest.fixture
def connection(tmp_path):
    data = {"version": 1, "device_id": str(uuid4()), "backend_url": "https://example.com",
            "writer_token": "sc_write_" + "test" * 12, "interval": 30,
            "security_consent": False, "consent_version": "monitor-v1"}
    path = tmp_path / "connection.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return data, path


@pytest.mark.parametrize("url", ["http://example.com", "https://user:secret@example.com", "https://example.com?key=secret", "https://example.com/path", "file:///tmp/test"])
def test_connection_rejects_insecure_or_ambiguous_destinations(connection, url):
    data, path = connection
    data["backend_url"] = url
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        watch.load_connection(str(path))


def test_watch_requires_consent_before_reading_or_collecting(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "load_connection", lambda path: pytest.fail("read config without consent"))
    args = argparse.Namespace(consent=False, config="missing", security_consent=False, once=True)
    assert watch.cmd_watch(args, AgentConfig(home=tmp_path)) == 2
    assert not list(tmp_path.iterdir())


def test_watch_stores_then_uploads_only_the_connected_device(connection, tmp_path, monkeypatch, capsys):
    data, path = connection
    monkeypatch.setattr(watch, "is_windows", lambda: True)
    monkeypatch.setattr(watch.HardwareCollector, "run", lambda self: CollectorResult(name="hardware", status="ok", data={"cpu": []}))
    monkeypatch.setattr(watch.PerformanceCollector, "run", lambda self: CollectorResult(name="performance", status="partial", error="C:/Users/private-name/error", data={"collect_errors": ["private error"]}))
    uploaded = []
    def fake_upload(snapshot, config):
        db = tmp_path / "monitor" / data["device_id"] / "agent.db"
        assert db.exists()
        uploaded.append(snapshot)
    monkeypatch.setattr(watch, "upload", fake_upload)
    args = argparse.Namespace(consent=True, config=str(path), security_consent=False, once=True)
    assert watch.cmd_watch(args, AgentConfig(home=tmp_path)) == 0
    assert len(uploaded) == 1 and uploaded[0]["device_id"] == data["device_id"]
    assert "security" not in uploaded[0]["sections"]
    assert "private-name" not in json.dumps(uploaded)
    assert "collect_errors" not in uploaded[0]["sections"]["performance"]["data"]
    assert data["writer_token"] not in capsys.readouterr().out
    with SnapshotStore(tmp_path / "monitor" / data["device_id"] / "agent.db") as store:
        assert list(watch.pending(store, data["device_id"], False)) == []


def test_pending_security_requires_current_consent_without_blocking_basic(tmp_path):
    with SnapshotStore(tmp_path / "agent.db") as store:
        for _ in range(12):
            store.save(build_snapshot([CollectorResult(name="security", status="ok")], device_id="device-a"))
        basic = build_snapshot([CollectorResult(name="performance", status="ok")], device_id="device-a")
        store.save(basic)
        store.save(build_snapshot([], device_id="other-device"))
        pending = list(watch.pending(store, "device-a", False))
        assert len(pending) == 1 and pending[0]["snapshot_id"] == basic["snapshot_id"]
        assert len(list(watch.pending(store, "device-a", True))) == 10


def test_upload_uses_header_and_never_follows_redirects(connection, monkeypatch):
    data, _ = connection
    captured = []
    class Response:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Opener:
        def open(self, request, **kwargs):
            captured.append(request)
            return Response()
    monkeypatch.setattr(watch.urllib.request, "build_opener", lambda handler: Opener())
    watch.upload({"snapshot_id": "synthetic"}, data)
    assert captured[0].get_header("Authorization") == "Bearer " + data["writer_token"]
    assert data["writer_token"] not in captured[0].full_url
    assert watch.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example") is None
