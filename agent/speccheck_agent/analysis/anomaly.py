"""M7: per-device z-score baseline, signals only (never diagnoses)."""
import statistics
from .common import features


def analyze(segment):
    signals = []
    usable = 0
    if not segment:
        return {'status': 'partial', 'reason': 'actual_device_history_required', 'signals': []}
    baseline = [features(s) for s in segment[:-1]]
    current = features(segment[-1])
    missing = []
    for key, value in current.items():
        values = [row[key] for row in baseline if key in row]
        if len(values) < 3:
            missing.append(key)
            continue
        usable += 1
        mean, std = statistics.mean(values), statistics.stdev(values)
        # Finite noise floor also handles a perfectly constant baseline.
        scale = max(std, abs(mean)*0.05, 1.0)
        z = (value-mean)/scale
        if abs(z) >= 3:
            signals.append({'metric': key, 'level': 'signal', 'z_score': round(z, 3),
                            'value': value, 'baseline_mean': mean, 'samples': len(values)})
    return {'status': 'ok' if usable and not missing else 'partial',
            'method': 'z_score', 'required_baseline_samples': 3, 'evaluated_metrics': usable,
            'insufficient_metrics': missing, 'signals': signals}
