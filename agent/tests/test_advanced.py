"""Milestone acceptance tests using synthetic measurements and Windows mocks."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from speccheck_agent.analysis import analyze_snapshot
from speccheck_agent.analysis.common import history_segment
from speccheck_agent.analysis import anomaly, trajectory, correlation
from speccheck_agent.collectors.base import CollectorResult
from speccheck_agent.collectors.security import SecurityCollector
from speccheck_agent.pipeline.store import SnapshotStore
from speccheck_agent.snapshot import build_snapshot
from speccheck_agent.win import cim, events


def snap(day, cpu=20, free=80, note=None, device='device-a'):
    t = (datetime(2026, 9, 1, tzinfo=timezone.utc)+timedelta(days=day)).isoformat()
    s = build_snapshot([
        CollectorResult('performance', 'ok', data={'samples': [{'timestamp': t, 'cpu_percent': cpu}],
                                                  'summary': {'cpu_percent': {'mean': cpu, 'max': cpu}}}),
        CollectorResult('storage_health', 'ok', data={'volumes': [{'is_system': True, 'free_percent': free}],
                                                     'disks': [{'disk_id': '0', 'wear_percent': day+10}]}),
    ], device_id=device, notes=note)
    s['collected_at'] = t
    return s


def test_sysmon_privacy_and_aggregation():
    raw = {'events': [{'event_id': 1, 'timestamp': '2026-09-01T00:00:12Z', 'process_key': 'a'*64,
                       'CommandLine': 'SECRET', 'User': 'PRIVATE', 'Image': 'C:\\Users\\PRIVATE\\x.exe',
                       'DestinationIp': '192.168.1.1', 'QueryName': 'secret.example'}]*2}
    result = events.aggregate(raw)
    assert result['counts'] == {'1': 2}
    assert result['buckets'][0]['count'] == 2
    serialized = json.dumps(result)
    for forbidden in ('SECRET', 'PRIVATE', 'Users', '192.168', 'secret.example', 'CommandLine', 'Image'):
        assert forbidden not in serialized


def test_sysmon_missing_keeps_security_state(monkeypatch):
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: json.dumps({'secure_boot': False, 'tpm_enabled': True,
                        'defender': {'antivirus_enabled': True, 'realtime_enabled': True}}))
    monkeypatch.setattr(events, 'query_events', lambda: {'status': 'skipped', 'events': []})
    result = SecurityCollector().collect()
    assert result['_partial']
    assert result['sysmon']['status'] == 'skipped'
    assert result['security_state']['secure_boot'] is False


def test_empty_log_is_not_missing(monkeypatch):
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: '{"status":"ok","events":[]}')
    assert events.query_events()['status'] == 'ok'
    assert events.aggregate(events.query_events())['counts'] == {}


def test_invalid_event_is_not_serialized():
    result = events.aggregate({'events': [{'event_id': 1, 'timestamp': 'secret'}]})
    assert result['rejected_events'] == 1 and not result['buckets']


def test_background_load_candidate_and_out_of_window():
    s = snap(0, cpu=95)
    t = s['collected_at']
    buckets = [{'timestamp': t, 'event_id': i, 'process_key': 'a'*64, 'count': 1} for i in (1, 3)]
    s['sections']['security'] = {'status': 'ok', 'data': {'sysmon': {'status': 'ok', 'buckets': buckets}}}
    result = correlation.analyze(s)
    assert result['candidates'][0]['action'] == 'software_fix'
    buckets[1]['timestamp'] = '2026-08-01T00:00:00Z'
    assert correlation.analyze(s)['conclusion'] == 'unknown'


def test_processes_must_match():
    s = snap(0, cpu=95)
    s['sections']['security'] = {'status': 'ok', 'data': {'sysmon': {'status': 'ok', 'buckets': [
        {'timestamp': s['collected_at'], 'event_id': 1, 'process_key': 'a'*64},
        {'timestamp': s['collected_at'], 'event_id': 3, 'process_key': 'b'*64}]}}}
    assert not correlation.analyze(s)['candidates']


def test_hardware_correlation_and_missing_data():
    s = snap(0)
    s['sections']['reliability'] = {'status': 'ok', 'data': {'buckets': [
        {'timestamp': s['collected_at'], 'kind': 'whea', 'count': 3},
        {'timestamp': s['collected_at'], 'kind': 'disk', 'count': 2}]}}
    result = correlation.analyze(s)
    assert result['candidates'][0]['purchase_candidate']
    assert result['candidates'][0]['evidence']['disk_count'] == 2
    s['sections']['reliability']['status'] = 'error'
    assert correlation.analyze(s)['conclusion'] == 'unknown'


def test_anomaly_cold_start_and_constant_baseline():
    assert anomaly.analyze([snap(0), snap(1)])['status'] == 'partial'
    result = anomaly.analyze([snap(i) for i in range(3)] + [snap(3, cpu=95)])
    assert any(s['metric'] == 'performance.cpu_percent' for s in result['signals'])
    assert all(s['level'] == 'signal' for s in result['signals'])
    assert not anomaly.analyze([snap(i) for i in range(4)])['signals']


def test_history_excludes_other_device_future_estimated_and_resets_notes():
    current = snap(5)
    estimated = snap(2)
    estimated['scan_mode'] = 'estimated'
    segment = history_segment(current, [snap(0), snap(1, device='other'), estimated, snap(3, note='repair'), snap(4), snap(6)])
    assert [s['collected_at'] for s in segment] == [snap(i)['collected_at'] for i in (3, 4, 5)]
    current['notes'] = 'replacement'
    assert history_segment(current, segment) == [current]


def test_trajectory_decline_and_uncertainty():
    result = trajectory.analyze([snap(i, free=40-10*i) for i in range(3)])
    trend = next(t for t in result['trends'] if t['metric'] == 'storage.free_percent')
    assert trend['slope_per_day'] == -10
    assert trend['threshold_at'] == '2026-09-04T00:00:00+00:00'
    assert trend['threshold_at_interval_approx'] is not None
    assert not trajectory.analyze([snap(0)])['trends']


def test_trajectory_stable_and_counter_reset():
    rows = [snap(i) for i in range(3)]
    rows[-1]['sections']['storage_health']['data']['disks'][0]['wear_percent'] = 0
    result = trajectory.analyze(rows)
    assert 'disk.0.wear_percent' in result['insufficient_metrics']
    assert next(t for t in result['trends'] if t['metric'] == 'storage.free_percent')['threshold_at'] is None


def test_analysis_estimated_and_failure_isolation(monkeypatch):
    s = snap(0)
    monkeypatch.setattr(correlation, 'analyze', Mock(side_effect=RuntimeError('PRIVATE')))
    analyze_snapshot(s, [])
    assert s['sections']['correlation']['status'] == 'error'
    assert s['sections']['anomaly']['status'] == 'partial'
    assert 'PRIVATE' not in json.dumps(s)
    s['scan_mode'] = 'estimated'
    analyze_snapshot(s, [])
    assert s['sections']['anomaly']['status'] == 'skipped'


def test_device_history_prune_and_cascade(tmp_path):
    with SnapshotStore(tmp_path/'agent.db') as store:
        for i in range(5):
            store.save(snap(i))
        other = snap(0, device='other')
        store.save(other)
        assert len(store.history('device-a', snap(3)['collected_at'])) == 3
        assert store.prune(2) == 3
        assert len(store.history('device-a', snap(10)['collected_at'])) == 2
        assert store.get(other['snapshot_id'])
        assert store.connect().execute('SELECT COUNT(*) FROM collector_runs').fetchone()[0] == 6


def test_powershell_timeout_exit_encoding(monkeypatch):
    monkeypatch.setattr(cim, 'is_windows', lambda: True)
    monkeypatch.setattr(subprocess, 'run', Mock(side_effect=subprocess.TimeoutExpired('powershell', 1)))
    with pytest.raises(cim.CimError):
        cim.run_powershell('test', timeout=1)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: Mock(returncode=1, stderr=b'PRIVATE'))
    with pytest.raises(cim.CimError) as exc:
        cim.run_powershell('test')
    assert 'PRIVATE' not in str(exc.value)
    run = Mock(return_value=Mock(returncode=0, stdout='\ufeff한글'.encode('utf-8')))
    monkeypatch.setattr(subprocess, 'run', run)
    assert cim.run_powershell('test') == '한글'
    assert '-EncodedCommand' in run.call_args.args[0]


def test_cli_json_and_unknown_collector(tmp_path, monkeypatch, capsys):
    from speccheck_agent import cli
    monkeypatch.setenv('SPECCHECK_AGENT_HOME', str(tmp_path))
    monkeypatch.setattr(cli, 'iter_collectors', lambda names: [])
    assert cli.main(['scan', '--json', '--no-save']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['sections']['trajectory']['status'] == 'partial'
    assert not (tmp_path/'agent.db').exists()


def test_collectors_windows_json_fixtures(monkeypatch):
    from speccheck_agent.collectors.performance import PerformanceCollector
    from speccheck_agent.collectors.storage_health import StorageHealthCollector
    from speccheck_agent.collectors.reliability import ReliabilityCollector
    rows = [{'timestamp': snap(0)['collected_at'], 'cpu_percent': c, 'memory_percent': 40, 'disk_queue': 0} for c in (10,20,30)]
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: json.dumps({'samples': rows}))
    assert PerformanceCollector().collect()['summary']['cpu_percent']['mean'] == 20
    monkeypatch.setattr(cim, 'run_powershell', lambda *a, **k: '{"volumes":[],"disks":[],"partial":true}')
    assert StorageHealthCollector().collect()['_partial']
    monkeypatch.setattr(events, 'query_events', lambda *a: {'status': 'skipped', 'events': []})
    monkeypatch.setattr(ReliabilityCollector, 'requires_windows', False)
    assert ReliabilityCollector().run().status == 'skipped'


def test_save_is_atomic_and_preserves_upload_marker(tmp_path):
    import sqlite3
    s = snap(0)
    with SnapshotStore(tmp_path/'agent.db') as store:
        store.save(s)
        store.mark_uploaded(s['snapshot_id'])
        store.save(s)
        assert store.list_recent()[0]['uploaded_at']
        broken = snap(1)
        broken['sections']['performance']['status'] = None
        with pytest.raises(sqlite3.IntegrityError):
            store.save(broken)
        assert store.get(broken['snapshot_id']) is None
        assert store.latest()['snapshot_id'] == s['snapshot_id']


@pytest.mark.parametrize('body', [b'not JSON', b'[]'])
def test_upload_invalid_response(body, monkeypatch):
    from speccheck_agent.transport import uploader
    response = Mock()
    response.read.return_value = body
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(uploader.urllib.request, 'urlopen', lambda *a, **k: context)
    with pytest.raises(uploader.UploadError):
        uploader.upload_snapshot(snap(0), 'http://localhost:8000')


def test_nonfinite_measurements_do_not_become_signals():
    result = anomaly.analyze([snap(i) for i in range(3)] + [snap(3, cpu=float('nan'))])
    assert not any(s['metric'] == 'performance.cpu_percent' for s in result['signals'])
    json.dumps(result, allow_nan=False)


def test_actual_cli_unknown_collector_and_prune_validation(tmp_path, monkeypatch, capsys):
    from speccheck_agent import cli
    monkeypatch.setenv('SPECCHECK_AGENT_HOME', str(tmp_path))
    assert cli.main(['scan', '--collectors', 'does-not-exist']) == 1
    assert 'Traceback' not in capsys.readouterr().err
    assert cli.main(['prune', '--keep', '0']) == 1


def test_missing_current_metric_does_not_predict():
    rows = [snap(i) for i in range(4)]
    rows[-1]['sections']['storage_health']['status'] = 'error'
    assert not trajectory.analyze(rows)['trends']
