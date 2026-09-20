"""Shared missing-data and chronological history handling."""
import math
from datetime import datetime, timezone


def timestamp(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def data(snapshot, name):
    section = snapshot.get('sections', {}).get(name, {})
    return section.get('data', {}) if section.get('status') in ('ok', 'partial') else {}


def features(snapshot):
    result = {}
    for key, summary in data(snapshot, 'performance').get('summary', {}).items():
        if isinstance(summary, dict) and number(summary.get('mean')):
            result['performance.' + key] = summary['mean']
    storage = data(snapshot, 'storage_health')
    for volume in storage.get('volumes', []):
        if volume.get('is_system') and number(volume.get('free_percent')):
            result['storage.free_percent'] = volume['free_percent']
    for disk in storage.get('disks', []):
        # Keep disks separate: averages could hide a failing drive.
        disk_id = str(disk.get('disk_id', ''))
        if not disk_id.isdecimal():
            continue
        for key in ('wear_percent', 'reallocated_sectors'):
            if number(disk.get(key)):
                result['disk.' + disk_id + '.' + key] = disk[key]
    reliability = data(snapshot, 'reliability')
    if not reliability.get('truncated') and number(reliability.get('whea_count')):
        result['reliability.whea_count_24h'] = reliability['whea_count']
    return result


def history_segment(current, history):
    """Only earlier actual measurements from this device; notes reset baseline."""
    end = timestamp(current.get('collected_at'))
    if not end or not current.get('device_id') or current.get('scan_mode') != 'actual':
        return []
    rows = {}
    for item in history:
        t = timestamp(item.get('collected_at'))
        if (t and t < end and item.get('device_id') == current['device_id']
                and item.get('scan_mode') == 'actual' and item.get('snapshot_id') != current.get('snapshot_id')):
            rows[t] = item
    ordered = [rows[t] for t in sorted(rows)] + [current]
    for index in range(len(ordered)-1, -1, -1):
        if ordered[index].get('notes'):
            return ordered[index:]
    return ordered
