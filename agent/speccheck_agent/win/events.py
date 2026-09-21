"""Bounded event queries: no messages, paths, users, commands or addresses."""
from __future__ import annotations
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from . import cim


def _write_setup_diagnostic(process: subprocess.CompletedProcess[bytes]) -> None:
    """Keep only setup runner diagnostics locally; telemetry never includes them."""
    directory = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SpecCheck" / "Sysmon"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        message = process.stderr.decode("utf-8", errors="replace").strip()
        if not message:
            message = process.stdout.decode("utf-8", errors="replace").strip()
        (directory / "setup-runner-error.txt").write_text(message[:4000], encoding="utf-8")
    except OSError:
        pass

EVENT_SCRIPT = r"""
$queryEnd = Get-Date
$queryStart = $queryEnd.AddHours(-24)
$result = @{start=$queryStart.ToUniversalTime().ToString('o'); end=$queryEnd.ToUniversalTime().ToString('o'); events=@(); status='ok'; truncated=$false}
try {
    $null = Get-WinEvent -ListLog '__CHANNEL__' -ErrorAction Stop
    try {
        $rows = @(Get-WinEvent -FilterHashtable @{LogName='__CHANNEL__'; Id=__IDS__; StartTime=$queryStart; EndTime=$queryEnd} -MaxEvents 2001 -ErrorAction Stop)
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

SYSMON_STATUS_SCRIPT = r"""
$result = @{status='skipped'; reason='sysmon_channel_unavailable'; enabled=$null; record_count=$null}
try {
    $log = Get-WinEvent -ListLog 'Microsoft-Windows-Sysmon/Operational' -ErrorAction Stop
    $result.status = 'ok'
    $result.enabled = [bool]$log.IsEnabled
    $result.record_count = [int64]$log.RecordCount
} catch {}
$result | ConvertTo-Json -Compress
"""


def sysmon_status() -> dict:
    """Check the optional Sysmon channel without reading any event payload."""
    try:
        raw = cim.run_powershell(SYSMON_STATUS_SCRIPT, timeout=5)
        value = json.loads(raw.lstrip("\ufeff"))
    except (cim.CimError, ValueError, TypeError, AttributeError):
        return {"status": "skipped", "reason": "sysmon_channel_unavailable"}
    if not isinstance(value, dict) or value.get("status") != "ok":
        return {"status": "skipped", "reason": "sysmon_channel_unavailable"}
    return {
        "status": "ok",
        "enabled": bool(value.get("enabled")),
        "record_count": value.get("record_count") if isinstance(value.get("record_count"), int) else None,
    }


def provision_sysmon() -> dict:
    """Install/configure Sysmon only from an already elevated Agent process."""
    if not cim.is_elevated():
        return {"status": "skipped", "reason": "sysmon_setup_requires_administrator"}
    script = Path(__file__).resolve().parents[3] / "scripts" / "enable-sysmon.ps1"
    config = script.parents[1] / "agent" / "sysmon-config.xml"
    if not script.is_file() or not config.is_file():
        return {"status": "skipped", "reason": "sysmon_setup_script_missing"}
    try:
        process = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-ConfigPath", str(config),
            ],
            capture_output=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "skipped", "reason": "sysmon_setup_failed"}
    if process.returncode != 0:
        _write_setup_diagnostic(process)
        return {"status": "skipped", "reason": "sysmon_setup_failed"}
    try:
        outcome = json.loads(process.stdout.decode("utf-8", errors="replace").lstrip("\ufeff"))
    except (json.JSONDecodeError, TypeError):
        outcome = {}
    if isinstance(outcome, dict) and outcome.get("status") == "restart_required":
        return {"status": "skipped", "reason": "sysmon_setup_restart_required"}
    status = sysmon_status()
    if status["status"] == "ok" and status.get("enabled"):
        return {"status": "ready"}
    return {"status": "skipped", "reason": "sysmon_setup_failed"}

def query_events(security: bool = True) -> dict:
    if security:
        availability = sysmon_status()
        if availability["status"] != "ok" or not availability.get("enabled"):
            return {
                "status": "skipped",
                "reason": availability.get("reason", "sysmon_channel_unavailable"),
                "events": [],
            }
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
