"""M5-M8 telemetry tests on the current Agent contract."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from speccheck_agent.analysis import analyze_snapshot
from speccheck_agent.analysis import anomaly, correlation, trajectory
from speccheck_agent.collectors.base import CollectorResult
from speccheck_agent.collectors.security import SecurityCollector
from speccheck_agent.snapshot import build_snapshot
from speccheck_agent.win import cim, events


def snapshot(day: int, *, cpu: float = 20, free: float = 80, note: str | None = None) -> dict:
    observed = (datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=day)).isoformat()
    value = build_snapshot([
        CollectorResult("performance", "ok", data={
            "observed_at": observed,
            "cpu": {"usage_percent": {"avg": cpu, "max": cpu, "min": cpu, "samples": [cpu]}},
            "memory": {"committed_percent": {"avg": 40, "max": 40, "min": 40, "samples": [40]}},
            "disk": {"queue_length": {"avg": 0, "max": 0, "min": 0, "samples": [0]}},
        }),
        CollectorResult("storage_health", "ok", data={
            "volumes": [{"is_system": True, "free_percent": free}],
            "disks": [{"index": 0, "wear_percent": day + 10}],
        }),
    ], device_id="advanced-test", notes=note)
    value["collected_at"] = observed
    return value


def test_sysmon_events_are_aggregated_without_private_fields():
    result = events.aggregate({"events": [{
        "event_id": 1, "timestamp": "2026-09-01T00:00:12Z", "process_key": "a" * 64,
        "CommandLine": "secret", "Image": "C:\\Users\\private.exe", "DestinationIp": "192.168.0.1",
    }]})

    assert result["counts"] == {"1": 1}
    encoded = json.dumps(result)
    assert "secret" not in encoded and "Users" not in encoded and "192.168" not in encoded


def test_sysmon_status_does_not_read_event_payloads(monkeypatch):
    monkeypatch.setattr(
        cim,
        "run_powershell",
        lambda *_args, **_kwargs: json.dumps({"status": "ok", "enabled": True, "record_count": 42}),
    )

    status = events.sysmon_status()

    assert status == {"status": "ok", "enabled": True, "record_count": 42}


def test_event_query_uses_local_time_bounds_and_normalizes_output_to_utc():
    assert "$queryEnd = Get-Date" in events.EVENT_SCRIPT
    assert "StartTime=$queryStart; EndTime=$queryEnd" in events.EVENT_SCRIPT
    assert "$queryStart.ToUniversalTime()" in events.EVENT_SCRIPT


def test_security_keeps_platform_state_when_sysmon_is_missing(monkeypatch):
    monkeypatch.setattr(cim, "run_powershell", lambda *_args, **_kwargs: json.dumps({
        "secure_boot": False, "tpm_enabled": True,
        "defender": {"antivirus_enabled": True, "realtime_enabled": True},
    }))
    monkeypatch.setattr(
        events,
        "query_events",
        lambda: {"status": "skipped", "reason": "sysmon_channel_unavailable", "events": []},
    )

    result = SecurityCollector().collect()

    assert result["_partial"] is True
    assert result["sysmon"]["status"] == "skipped"
    assert result["sysmon"]["reason"] == "sysmon_channel_unavailable"
    assert result["security_state"]["secure_boot"] is False


def test_security_auto_provisions_then_retries_event_collection(monkeypatch):
    monkeypatch.setenv("SPECCHECK_SYSMON_AUTO_SETUP", "1")
    monkeypatch.setattr(cim, "run_powershell", lambda *_args, **_kwargs: json.dumps({
        "secure_boot": True, "tpm_enabled": True,
        "defender": {"antivirus_enabled": True, "realtime_enabled": True},
    }))
    responses = iter([
        {"status": "skipped", "reason": "sysmon_channel_unavailable", "events": []},
        {"status": "ok", "events": [], "start": "2026-09-01T00:00:00Z", "end": "2026-09-01T00:01:00Z"},
    ])
    monkeypatch.setattr(events, "query_events", lambda: next(responses))
    monkeypatch.setattr(events, "provision_sysmon", lambda: {"status": "ready"})

    result = SecurityCollector().collect()

    assert result["sysmon"]["status"] == "ok"
    assert result["sysmon"]["setup_status"] == "ready"
    assert result["_partial"] is False


def test_correlation_finds_software_and_hardware_candidates():
    value = snapshot(0, cpu=95)
    observed = value["collected_at"]
    value["sections"]["security"] = {"status": "ok", "data": {"sysmon": {"status": "ok", "buckets": [
        {"timestamp": observed, "event_id": 1, "process_key": "a" * 64, "count": 1},
        {"timestamp": observed, "event_id": 3, "process_key": "a" * 64, "count": 1},
    ]}}}
    value["sections"]["reliability"] = {"status": "ok", "data": {"events": [
        {"category": "whea_corrected", "last_at": observed, "count": 2},
        {"category": "disk_error", "last_at": observed, "count": 1},
    ]}}

    result = correlation.analyze(value)

    assert {item["id"] for item in result["candidates"]} == {"background_load", "hardware_instability"}


def test_anomaly_and_trajectory_use_local_history_only():
    history = [snapshot(index, cpu=20, free=50 - index * 10) for index in range(4)]
    history[-1]["sections"]["performance"]["data"]["cpu"]["usage_percent"]["avg"] = 95
    anomaly_result = anomaly.analyze(history)
    trajectory_result = trajectory.analyze(history)

    assert any(signal["metric"] == "performance.cpu.usage_percent" for signal in anomaly_result["signals"])
    free_space = next(item for item in trajectory_result["trends"] if item["metric"] == "storage.free_percent")
    assert free_space["threshold_at"] is not None


def test_note_resets_baseline_and_analysis_failure_stays_isolated():
    current = snapshot(4)
    current["notes"] = "SSD 교체 후"
    analyze_snapshot(current, [snapshot(0), snapshot(1), snapshot(2), snapshot(3)])

    assert current["sections"]["anomaly"]["status"] == "partial"
    assert current["sections"]["trajectory"]["status"] == "partial"
    assert current["sections"]["correlation"]["status"] in {"partial", "ok"}
