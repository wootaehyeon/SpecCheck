"""Bounded event queries: no messages, paths, users, commands or addresses."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
import re
from . import cim

EVENT_SCRIPT = r"""
$end = [DateTime]::UtcNow
$start = $end.AddHours(-24)
$result = @{start=$start.ToString('o'); end=$end.ToString('o'); events=@(); status='ok'; truncated=$false}
try {
    $null = Get-WinEvent -ListLog '__CHANNEL__' -ErrorAction Stop
    try {
        $rows = @(Get-WinEvent -FilterHashtable @{LogName='__CHANNEL__'; Id=__IDS__; StartTime=$start; EndTime=$end} -MaxEvents 2001 -ErrorAction Stop)
    } catch {
        if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { $rows = @() }
        else { throw }
    }
    $result.truncated = $rows.Count -gt 2000
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $result.events = @($rows | Select-Object -First 2000 | ForEach-Object {
        $evt = $_
        $row = @{event_id=[int]$evt.Id; timestamp=$evt.TimeCreated.ToUniversalTime().ToString('o')}
        if ('__CHANNEL__' -eq 'System') {
            if ($evt.ProviderName -eq 'Microsoft-Windows-WHEA-Logger') { $row.kind='whea' }
            elseif ($evt.ProviderName -in @('disk','storahci','stornvme','Microsoft-Windows-StorPort')) { $row.kind='disk' }
            else { $row.kind='other' }
        } else {
            [xml]$xml = $evt.ToXml()
            foreach ($field in $xml.Event.EventData.Data) {
                if ($field.Name -eq 'ProcessGuid') {
                    $bytes = [Text.Encoding]::UTF8.GetBytes([string]$field.'#text')
                    $row.process_key = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLower()
                }
            }
        }
        $row
    })
    $sha.Dispose()
} catch {
    $result.status = 'skipped'
    $result.reason = 'event_log_unavailable_or_access_denied'
}
$result | ConvertTo-Json -Depth 5 -Compress
"""

def query_events(security: bool = True) -> dict:
    channel = 'Microsoft-Windows-Sysmon/Operational' if security else 'System'
    ids = '1,3,11,13,22' if security else '7,17,18,19,20,46,47,51,129,153'
    raw = cim.run_powershell(EVENT_SCRIPT.replace('__CHANNEL__', channel).replace('__IDS__', ids), timeout=10)
    try:
        result = json.loads(raw.lstrip('\ufeff'))
        if not isinstance(result, dict) or not isinstance(result.get('events'), list):
            raise ValueError
        return result
    except (ValueError, TypeError) as exc:
        raise cim.CimError('Invalid event query response') from exc

def aggregate(result: dict) -> dict:
    """Minute/process buckets; newest 2000 events only, raw payloads discarded."""
    buckets, counts = Counter(), Counter()
    rejected = 0
    for row in result.get('events', [])[:2000]:
        try:
            event_id = int(row['event_id'])
            moment = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            if moment.tzinfo is None:
                raise ValueError
            minute = moment.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
            process = row.get('process_key')
            process = process if isinstance(process, str) and re.fullmatch('[a-f0-9]{64}', process) else None
            kind = row.get('kind') if row.get('kind') in ('whea', 'disk', 'other') else 'sysmon'
        except (KeyError, ValueError, TypeError, AttributeError):
            rejected += 1
            continue
        counts[str(event_id)] += 1
        buckets[(minute, process, kind, event_id)] += 1
    return {'window_start': result.get('start'), 'window_end': result.get('end'),
            'counts': dict(counts), 'truncated': bool(result.get('truncated')), 'rejected_events': rejected,
            'buckets': [dict(timestamp=k[0], process_key=k[1], kind=k[2], event_id=k[3], count=v)
                        for k, v in sorted(buckets.items(), key=lambda x: x[0][0])]}
