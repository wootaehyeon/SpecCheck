"""M6: ranked, time-window associations, not proof of causation."""
from .common import data, timestamp, number


def analyze(snapshot, window_seconds=120):
    security = data(snapshot, 'security').get('sysmon', {})
    reliability = data(snapshot, 'reliability')
    performance = data(snapshot, 'performance')
    samples = performance.get('samples', [])
    if not samples:
        cpu = ((performance.get('cpu') or {}).get('usage_percent') or {}).get('max')
        observed = performance.get('observed_at')
        samples = [{'timestamp': observed, 'cpu_percent': cpu}] if observed else []
    buckets = security.get('buckets', []) if security.get('status') == 'ok' else []
    hardware = reliability.get('buckets', [])
    if not hardware:
        hardware = [
            {
                'timestamp': event.get('last_at') or event.get('first_at'),
                'kind': 'whea' if str(event.get('category')).startswith('whea_') else 'disk',
                'count': event.get('count', 0),
            }
            for event in reliability.get('events', [])
            if str(event.get('category')).startswith('whea_') or event.get('category') in {'disk_error', 'filesystem_error'}
        ]
    candidates = []

    def near(a, b):
        ta, tb = timestamp(a.get('timestamp')), timestamp(b.get('timestamp'))
        return ta is not None and tb is not None and abs((ta-tb).total_seconds()) <= window_seconds

    for sample in samples:
        cpu = sample.get('cpu_percent')
        if not number(cpu) or cpu < 80:
            continue
        relevant = [b for b in buckets if near(sample, b) and b.get('process_key')]
        processes = {}
        for bucket in relevant:
            processes.setdefault(bucket['process_key'], set()).add(bucket.get('event_id'))
        for process, ids in processes.items():
            if 1 in ids and (3 in ids or 22 in ids):
                candidates.append({'id': 'background_load', 'confidence': 0.65,
                                   'action': 'software_fix', 'process_key': process,
                                   'summary': 'High CPU overlaps process creation and network activity; inspect background workload.',
                                   'evidence': {'cpu_percent': cpu, 'timestamp': sample['timestamp'],
                                                'event_ids': sorted(ids), 'window_seconds': window_seconds}})
    whea = [b for b in hardware if b.get('kind') == 'whea' and b.get('count', 0) > 0]
    disk = [b for b in hardware if b.get('kind') == 'disk' and b.get('count', 0) > 0]
    for a in whea:
        matching = [b for b in disk if near(a, b)]
        if matching:
            candidates.append({'id': 'hardware_instability', 'confidence': 0.75,
                               'action': 'hardware_inspection', 'purchase_candidate': True,
                               'summary': 'WHEA errors overlap disk errors; inspect hardware before deciding on replacement.',
                               'evidence': {'timestamp': a['timestamp'], 'whea_count': a['count'],
                                            'disk_count': sum(b['count'] for b in matching),
                                            'window_seconds': window_seconds}})
            break
    unique = {}
    for candidate in sorted(candidates, key=lambda c: c['confidence'], reverse=True):
        key = (candidate['id'], candidate.get('process_key'))
        unique.setdefault(key, candidate)
    ranked = list(unique.values())[:3]
    for rank, candidate in enumerate(ranked, 1):
        candidate['rank'] = rank
    complete = bool(samples) and security.get('status') == 'ok' and bool(reliability)
    complete = complete and not security.get('truncated') and not reliability.get('truncated')
    return {'status': 'ok' if complete else 'partial', 'candidates': ranked,
            'conclusion': 'candidate_causes' if ranked else 'unknown', 'window_seconds': window_seconds}
