"""M8: linear trends with residual uncertainty; no physical lifetime claims."""
import math
import statistics
from datetime import timedelta
from .common import features, timestamp


def analyze(segment):
    trends, insufficient = [], []
    if len(segment) < 3:
        return {'status': 'partial', 'required_samples': 3, 'trends': [], 'reason': 'insufficient_history'}
    keys = {k for s in segment for k in features(s) if not k.startswith('performance.')}
    for key in sorted(keys):
        if key not in features(segment[-1]):
            insufficient.append(key)
            continue
        points = [(timestamp(s['collected_at']), features(s)[key]) for s in segment if key in features(s)]
        if len(points) < 3 or (points[-1][0]-points[0][0]).total_seconds() < 86400:
            insufficient.append(key)
            continue
        # Counter reset / replacement invalidates wear and sector extrapolation.
        if key.startswith('disk.') and any(b[1] < a[1] for a, b in zip(points, points[1:])):
            insufficient.append(key)
            continue
        xs = [(t-points[0][0]).total_seconds()/86400 for t, _ in points]
        ys = [v for _, v in points]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x-mx)**2 for x in xs)
        slope = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/sxx
        intercept = my-slope*mx
        variance = sum((y-intercept-slope*x)**2 for x, y in zip(xs, ys))/(len(xs)-2)
        se = math.sqrt(variance/sxx)
        threshold = 10 if key.endswith('free_percent') else 90 if key.endswith('wear_percent') else 1 if key.endswith('reallocated_sectors') else None
        predicted = None
        interval = None
        last_fit = intercept+slope*xs[-1]
        declining = key.endswith('free_percent')
        adverse = slope < 0 if declining else slope > 0
        if threshold is not None and adverse:
            days = (threshold-last_fit)/slope
            if 0 <= days <= 3650:
                predicted = (points[-1][0]+timedelta(days=days)).isoformat()
                bounds = []
                for candidate in (slope-2*se, slope+2*se):
                    if candidate and (candidate < 0 if declining else candidate > 0):
                        d = (threshold-last_fit)/candidate
                        if 0 <= d <= 3650:
                            bounds.append((points[-1][0]+timedelta(days=d)).isoformat())
                if len(bounds) == 2:
                    interval = sorted(bounds)
        trends.append({'metric': key, 'samples': len(points), 'slope_per_day': slope,
                       'slope_interval_approx': [slope-2*se, slope+2*se], 'threshold': threshold,
                       'threshold_at': predicted, 'threshold_at_interval_approx': interval,
                       'interpretation': 'observed_trend_not_failure_prediction'})
    return {'status': 'ok' if trends and not insufficient else 'partial', 'method': 'linear_regression',
            'required_samples': 3, 'minimum_span_days': 1, 'insufficient_metrics': insufficient, 'trends': trends}
