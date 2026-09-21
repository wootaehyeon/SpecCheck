"""Bounded event queries: no messages, paths, users, commands or addresses."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
import re
from . import cim

SYSMON_REASONS = {
    'not_installed': 'Sysmon is not installed. Run scripts/setup-sysmon.ps1 in Administrator PowerShell from the repository root.',
    'log_missing': 'Sysmon service exists but its event log is missing. Repair the Sysmon installation.',
    'log_disabled': 'Sysmon event log is disabled. Enable Microsoft-Windows-Sysmon/Operational in Event Viewer.',
    'access_denied': 'Sysmon event log access denied. Run doctor as administrator or grant this user read access with scripts/grant-sysmon-read.ps1 (see docs/ADVANCED_SCAN.md).',
    'service_stopped': 'Sysmon service is stopped. Start the installed Sysmon service in Administrator PowerShell.',
    'query_failed': 'Sysmon event query failed. Check the event log and retry doctor.',
}

# Error identifiers are stable across Windows display languages. Never expose
# exception messages, which may contain paths or other local information.
ERROR_CLASSIFIER = r"""
    if ($_.CategoryInfo.Category -eq 'PermissionDenied' -or $_.Exception -is [UnauthorizedAccessException] -or $_.Exception.InnerException -is [UnauthorizedAccessException] -or $_.Exception.HResult -eq -2147024891 -or $_.Exception.InnerException.HResult -eq -2147024891) {
        $result.reason = 'access_denied'
    } elseif ($_.FullyQualifiedErrorId -like 'NoMatchingLogsFound*' -or $_.Exception -is [System.Diagnostics.Eventing.Reader.EventLogNotFoundException] -or $_.Exception.InnerException -is [System.Diagnostics.Eventing.Reader.EventLogNotFoundException]) {
        $services = @(Get-Service -Name Sysmon,Sysmon64,Sysmon64a -ErrorAction SilentlyContinue)
        $result.reason = if ($services.Count -eq 0) { 'not_installed' } else { 'log_missing' }
    } elseif ($_.Exception.Message -eq 'speccheck_channel_disabled') {
        $result.reason = 'log_disabled'
    } else {
        $result.status = 'error'
        $result.reason = 'query_failed'
    }
"""

PROBE_SCRIPT = r"""
$result = @{status='ok'}
try {
    $log = [System.Diagnostics.Eventing.Reader.EventLogConfiguration]::new('Microsoft-Windows-Sysmon/Operational')
    try { $enabled = $log.IsEnabled } finally { $log.Dispose() }
    if (-not $enabled) { throw 'speccheck_channel_disabled' }
    $services = @(Get-Service -Name Sysmon,Sysmon64,Sysmon64a -ErrorAction SilentlyContinue)
    if ($services.Count -gt 0 -and @($services | Where-Object Status -eq Running).Count -eq 0) {
        $result.status='skipped'; $result.reason='service_stopped'
    } else {
        try { $null = Get-WinEvent -LogName 'Microsoft-Windows-Sysmon/Operational' -MaxEvents 1 -ErrorAction Stop }
        catch { if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw } }
    }
} catch {
    $result.status = 'skipped'
    __CLASSIFY__
}
$result | ConvertTo-Json -Compress
""".replace('__CLASSIFY__', ERROR_CLASSIFIER)


def probe_sysmon():
    """Check service/channel/read access without scanning 24 hours of events."""
    try:
        result = json.loads(cim.run_powershell(PROBE_SCRIPT, timeout=10).lstrip('\ufeff'))
        if not isinstance(result, dict) or result.get('status') not in ('ok', 'skipped', 'error'):
            raise ValueError
        code = result.get('reason', 'query_failed')
        return {'status': result['status'], 'reason_code': None if result['status'] == 'ok' else code if code in SYSMON_REASONS else 'query_failed',
                'reason': 'service and event log readable' if result['status'] == 'ok' else SYSMON_REASONS.get(code, SYSMON_REASONS['query_failed'])}
    except (cim.CimError, ValueError, TypeError):
        return {'status': 'error', 'reason_code': 'query_failed', 'reason': SYSMON_REASONS['query_failed']}

EVENT_SCRIPT = r"""
$end = [DateTime]::UtcNow
$start = $end.AddHours(-24)
$result = @{start=$start.ToString('o'); end=$end.ToString('o'); events=@(); status='ok'; truncated=$false}
try {
    $log = [System.Diagnostics.Eventing.Reader.EventLogConfiguration]::new('__CHANNEL__')
    try { $enabled = $log.IsEnabled } finally { $log.Dispose() }
    if (-not $enabled) { throw 'speccheck_channel_disabled' }
    # Explicit UTC XPath avoids Get-WinEvent's local-time hashtable conversion.
    # EventLogReader streams records without cmdlet materialization overhead.
    $ids = @(__IDS__)
    $idFilter = ($ids | ForEach-Object { "EventID=$_" }) -join ' or '
    $startText = $start.ToString('o')
    $endText = $end.ToString('o')
    $filter = "*[System[($idFilter) and TimeCreated[@SystemTime >= '$startText' and @SystemTime <= '$endText']]]"
    $query = [System.Diagnostics.Eventing.Reader.EventLogQuery]::new('__CHANNEL__', [System.Diagnostics.Eventing.Reader.PathType]::LogName, $filter)
    $query.ReverseDirection = $true
    $reader = [System.Diagnostics.Eventing.Reader.EventLogReader]::new($query)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $rows = [System.Collections.Generic.List[object]]::new()
    try {
      while ($null -ne ($evt = $reader.ReadEvent())) {
       try {
        if ($rows.Count -ge 2000) { $result.truncated = $true; break }
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
        $rows.Add($row)
       } finally { $evt.Dispose() }
      }
      $result.events = $rows.ToArray()
    } finally {
        $reader.Dispose()
        $sha.Dispose()
    }
} catch {
    $result.status = 'skipped'
    __CLASSIFY__
}
$result | ConvertTo-Json -Depth 5 -Compress
""".replace('__CLASSIFY__', ERROR_CLASSIFIER)

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
