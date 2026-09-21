"""Attach independently isolated local analysis results to snapshot sections."""
from . import anomaly, correlation, trajectory
from .common import history_segment


def analyze_snapshot(snapshot, history):
    segment = history_segment(snapshot, history)
    jobs = [('correlation', 'M6', lambda: correlation.analyze(snapshot)),
            ('anomaly', 'M7', lambda: anomaly.analyze(segment)),
            ('trajectory', 'M8', lambda: trajectory.analyze(segment))]
    for name, milestone, run in jobs:
        try:
            if snapshot.get('scan_mode') != 'actual':
                result = {'status': 'skipped', 'reason': 'actual_measurements_required'}
            else:
                result = run()
            status = result.pop('status')
            section = {'status': status, 'milestone': milestone, 'data': result}
        except Exception:
            # Do not serialize exception text, which may contain raw telemetry.
            section = {'status': 'error', 'milestone': milestone, 'error': 'analysis_failed', 'data': {}}
        snapshot['sections'][name] = section
    return snapshot
