"""System event aggregates for WHEA and disk retries; no event messages."""
from .base import Collector, register
from ..win import events, cim

@register
class ReliabilityCollector(Collector):
    name = 'reliability'
    milestone = 'M2'
    description = 'WHEA / disk error minute aggregates'

    def collect(self):
        raw = events.query_events(False)
        if raw.get('status') == 'error':
            raise cim.CimError('System event query failed')
        result = events.aggregate(raw)
        result['_skipped'] = raw.get('status') == 'skipped'
        if result['_skipped']:
            result['_reason'] = 'System event log unavailable or access denied'
        result['_partial'] = result['truncated'] or bool(result['rejected_events'])
        result['whea_count'] = sum(b['count'] for b in result['buckets'] if b['kind'] == 'whea')
        result['disk_error_count'] = sum(b['count'] for b in result['buckets'] if b['kind'] == 'disk')
        return result
