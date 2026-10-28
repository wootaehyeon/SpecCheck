import json
import base64
import platform
import subprocess
from datetime import datetime, timezone

import pytest

from speccheck_agent.collectors import security
from speccheck_agent.cli import main
from speccheck_agent.pipeline import SnapshotStore
from speccheck_agent.snapshot import build_snapshot
from speccheck_agent.collectors.base import CollectorResult


def event(record=1, event_id=1):
    return {"record_id": record, "event_id": event_id,
            "occurred_at": "2026-09-14T10:00:00Z", "process_guid": "guid",
            "process_id": "45", "image": r"C:\Users\private\app.exe",
            "command_line": "secret", "user": "private"}


def test_no_consent_never_reads_sysmon(monkeypatch):
    monkeypatch.setattr(security, "run_powershell", lambda *_: pytest.fail("read without consent"))
    assert security.SecurityCollector().run().status == "skipped"
    with pytest.raises(PermissionError):
        security.SecurityCollector().collect()
    assert main(["monitor"]) == 2


def test_normalization_removes_sensitive_fields():
    result = security.normalize_event(event())
    assert result["image"] == "app.exe"
    assert "user" not in result and "command_line" not in result
    assert result["occurred_at"] == "2026-09-14T10:00:00+00:00"


@pytest.mark.parametrize("code", ["access_denied", "log_unavailable", "log_disabled"])
def test_monitor_stops_on_configuration_failure_without_saving_or_uploading(code, monkeypatch, tmp_path, capsys):
    from speccheck_agent import cli

    monkeypatch.setattr(cli, "is_elevated", lambda: True)
    monkeypatch.setenv("SPECCHECK_AGENT_HOME", str(tmp_path))
    monkeypatch.setattr(security.SecurityCollector, "requires_windows", False)
    monkeypatch.setattr(security, "run_powershell", lambda *_: json.dumps({"collection_error": code}))
    monkeypatch.setattr(cli.time, "sleep", lambda *_: pytest.fail("must not retry configuration error"))
    monkeypatch.setattr(cli, "upload_snapshot", lambda *_: pytest.fail("must not upload after access failure"))
    assert cli.main(["monitor", "--security-consent", "--upload"]) == 2
    assert "수집 중단" in capsys.readouterr().err
    with SnapshotStore(tmp_path / "agent.db") as store:
        assert store.count() == 0


@pytest.mark.skipif(platform.system() != "Windows", reason="PowerShell exception handling")
def test_powershell_permission_error_is_classified_without_reading_logs():
    # Shadow the cmdlet: exercise the actual catch block without accessing Sysmon.
    stub = "function Get-WinEvent { throw [System.UnauthorizedAccessException]::new('localized error') }; "
    result = json.loads(security.run_powershell(stub + security.build_script(datetime.now(timezone.utc))))
    assert result["collection_error"] == "access_denied"


@pytest.mark.parametrize("approved,expected", [(True, 0), (False, 2)])
def test_monitor_requests_uac_before_any_collection(approved, expected, monkeypatch):
    from speccheck_agent import cli
    calls = []
    monkeypatch.setattr(cli, "is_windows", lambda: True)
    monkeypatch.setattr(cli, "is_elevated", lambda: False)
    monkeypatch.setattr(cli, "request_monitor_elevation", lambda config, interval, upload: calls.append((interval, upload)) or approved)
    monkeypatch.setattr(cli, "SnapshotStore", lambda *_: pytest.fail("parent must not open DB"))
    monkeypatch.setattr(cli, "SecurityCollector", lambda **_: pytest.fail("parent must not collect"))
    assert cli.main(["monitor", "--security-consent", "--interval", "60", "--upload"]) == expected
    assert calls == [(60, True)]


def test_elevated_child_does_not_loop_uac(monkeypatch):
    from speccheck_agent import cli
    monkeypatch.setattr(cli, "is_windows", lambda: True)
    monkeypatch.setattr(cli, "is_elevated", lambda: False)
    monkeypatch.setattr(cli, "request_monitor_elevation", lambda *_: pytest.fail("repeated UAC"))
    assert cli.main(["monitor", "--security-consent", "--elevated-child"]) == 2


def test_elevation_preserves_settings_as_data(monkeypatch, tmp_path):
    from speccheck_agent.win import elevation
    from speccheck_agent.config import AgentConfig
    captured = []
    monkeypatch.setattr(elevation.subprocess, "run", lambda argv, **kw: captured.append(argv) or subprocess.CompletedProcess(argv, 0))
    cfg = AgentConfig(home=tmp_path / "한글 user's data", backend_url="https://example.test", device_id="original-device")
    assert elevation.request_monitor_elevation(cfg, 45, True)
    script = captured[0][-1]
    assert "-Verb RunAs" in script and "--elevated-child" in script
    assert "user''s data" in script and "original-device" in script
    assert "https://example.test" in script and "--upload" in script


def test_cursor_advances_only_after_save_ack_and_cap_marks_partial(monkeypatch):
    monkeypatch.setattr(security, "EVENT_LIMIT", 2)
    payload = {"events": [event(1), event(2), event(3)],
               "log_oldest_at": "2026-09-14T00:00:00Z", "log_reset": False}
    monkeypatch.setattr(security, "run_powershell", lambda *_: json.dumps(payload))
    collector = security.SecurityCollector(True, datetime(2026, 9, 14, 9, tzinfo=timezone.utc))
    data = collector.collect()
    assert collector.after_record == 0
    assert data["truncated"] and data["_partial"] and len(data["events"]) == 2
    collector.acknowledge(data)
    assert collector.after_record == 2
    assert collector.anchor_time == "2026-09-14T10:00:00+00:00"


def test_log_reset_resets_cursor_when_empty(monkeypatch):
    payload = {"events": [], "log_oldest_at": "2026-09-14T11:00:00Z", "log_reset": True}
    monkeypatch.setattr(security, "run_powershell", lambda *_: json.dumps(payload))
    collector = security.SecurityCollector(True)
    collector.after_record = 100
    data = collector.collect()
    assert data["log_gap"] and data["_partial"]
    collector.acknowledge(data)
    assert collector.after_record == 0


def test_pending_uploads_exclude_basic_scans(tmp_path):
    with SnapshotStore(tmp_path / "agent.db") as store:
        store.save(build_snapshot([CollectorResult("hardware", "ok")]))
        snapshot = build_snapshot([CollectorResult("security", "ok")])
        store.save(snapshot)
        assert [s["snapshot_id"] for s in store.pending_security_uploads()] == [snapshot["snapshot_id"]]
        store.mark_uploaded(snapshot["snapshot_id"])
        assert not store.pending_security_uploads()


@pytest.mark.skipif(platform.system() != "Windows", reason="PowerShell parser")
def test_powershell_script_parses_without_reading_logs():
    script = security.build_script(datetime.now(timezone.utc), 10, "2026-09-14T10:00:00+00:00")
    encoded = base64.b64encode(script.encode()).decode()
    parser = (
        "$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')); "
        "$tokens = $null; $parseErrors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors); "
        "if ($parseErrors.Count) { $parseErrors | Out-String | Write-Output; exit 1 }"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", parser], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
