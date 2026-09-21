"""Sysmon diagnostics must distinguish absent logs from read errors."""
import json

import pytest

from speccheck_agent import cli
from speccheck_agent.config import AgentConfig
from speccheck_agent.win import cim, events
from speccheck_agent.collectors.security import SecurityCollector


@pytest.mark.parametrize('reason', ['not_installed', 'log_missing', 'log_disabled', 'access_denied', 'service_stopped', 'query_failed'])
def test_probe_preserves_reason_and_action(monkeypatch, reason):
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: json.dumps({'status': 'skipped', 'reason': reason}))
    result = events.probe_sysmon()
    assert result['reason_code'] == reason
    assert result['reason'] == events.SYSMON_REASONS[reason]
    assert result['status'] != 'ok'


@pytest.mark.parametrize('raw', ['[]', 'null', 'not json', '{"status":"unknown"}'])
def test_bad_probe_output_does_not_claim_uninstalled(monkeypatch, raw):
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: raw)
    result = events.probe_sysmon()
    assert result['status'] == 'error'
    assert result['reason_code'] == 'query_failed'


def test_probe_timeout_is_not_reported_as_missing_installation(monkeypatch):
    def timeout(*a, **k):
        raise cim.CimError('timeout')
    monkeypatch.setattr(cim, 'run_powershell', timeout)
    assert events.probe_sysmon()['reason_code'] == 'query_failed'


def test_event_buckets_normalize_korean_and_utc_times():
    result = events.aggregate({'events': [
        {'event_id': 1, 'timestamp': '2026-09-21T21:00:01+09:00', 'process_key': 'a'*64},
        {'event_id': 1, 'timestamp': '2026-09-21T12:00:30Z', 'process_key': 'a'*64},
    ]})
    assert len(result['buckets']) == 1
    assert result['buckets'][0]['timestamp'] == '2026-09-21T12:00:00+00:00'
    assert result['buckets'][0]['count'] == 2


def test_collector_preserves_missing_log_reason(monkeypatch):
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: '{}')
    monkeypatch.setattr(events, 'query_events', lambda: {'events': [], 'status': 'skipped', 'reason': 'not_installed'})
    result = SecurityCollector().collect()
    assert result['sysmon']['reason_code'] == 'not_installed'
    assert 'setup-sysmon.ps1' in result['sysmon']['reason']


@pytest.mark.parametrize('status,badge', [('ok', '[OK]'), ('skipped', '[WARN]'), ('error', '[WARN]')])
def test_doctor_optional_sysmon_is_not_a_false_ok(monkeypatch, tmp_path, capsys, status, badge):
    import ctypes
    from types import SimpleNamespace
    monkeypatch.setattr(cli.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: 'test')
    monkeypatch.setattr(events, 'probe_sysmon', lambda: {'status': status, 'reason': 'test reason'})
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: False)), raising=False)
    assert cli.cmd_doctor(None, AgentConfig(home=tmp_path)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert next(line for line in lines if 'Sysmon (optional)' in line).startswith(badge)
    assert 'Sysmon (optional) ' in next(line for line in lines if 'Sysmon (optional)' in line)
    assert next(line for line in lines if 'Admin (optional)' in line).startswith('[WARN]')
