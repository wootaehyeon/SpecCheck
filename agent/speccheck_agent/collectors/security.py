"""Opt-in Sysmon collection; never installs or configures Sysmon."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import PureWindowsPath
from typing import Any

from .base import Collector, register
from ..win.cim import CimError, run_powershell

EVENT_LIMIT = 2000


def build_script(since: datetime, after_record: int = 0, anchor_time: str | None = None) -> str:
    stamp = since.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    anchor = (datetime.fromisoformat(anchor_time).astimezone(timezone.utc)
              .isoformat(timespec="milliseconds").replace("+00:00", "Z")) if anchor_time else ""
    return r"""
try {
$log = 'Microsoft-Windows-Sysmon/Operational'
$info = Get-WinEvent -ListLog $log -ErrorAction Stop
if (-not $info.IsEnabled) {
    @{ collection_error = 'log_disabled' } | ConvertTo-Json -Compress
    return
}
$oldest = Get-WinEvent -LogName $log -Oldest -MaxEvents 1 -ErrorAction Stop
$latest = Get-WinEvent -LogName $log -MaxEvents 1 -ErrorAction Stop
$after = AFTER_RECORD
$reset = ($after -gt 0 -and $latest.RecordId -lt $after)
$cursorMissing = ($after -gt 0 -and $oldest.RecordId -gt $after)
if ($after -gt 0 -and -not $reset -and -not $cursorMissing -and 'ANCHOR' -ne '') {
    $previous = Get-WinEvent -LogName $log -FilterXPath "*[System[EventRecordID=$after]]" -MaxEvents 1 -ErrorAction Stop
    if ($previous.TimeCreated.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ") -ne 'ANCHOR') { $reset = $true }
}
if ($reset) { $after = 0 }
$xpath = "*[System[(EventID=1 or EventID=5 or EventID=25 or EventID=255) and TimeCreated[@SystemTime >= 'SINCE'] and EventRecordID > $after]]"
$rows = @()
try {
    $rows = @(Get-WinEvent -LogName $log -FilterXPath $xpath -Oldest -MaxEvents LIMIT -ErrorAction Stop)
} catch {
    if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }
}
$events = @($rows | ForEach-Object {
    $evt = $_
    $xml = [xml]$evt.ToXml()
    $fields = @{}
    foreach ($item in $xml.Event.EventData.Data) { $fields[$item.Name] = [string]$item.'#text' }
    [ordered]@{
        event_id = [int]$evt.Id
        record_id = [long]$evt.RecordId
        occurred_at = $evt.TimeCreated.ToUniversalTime().ToString('o')
        process_guid = $fields['ProcessGuid']
        process_id = $fields['ProcessId']
        image = [System.IO.Path]::GetFileName($fields['Image'])
        parent_process_guid = $fields['ParentProcessGuid']
        parent_image = [System.IO.Path]::GetFileName($fields['ParentImage'])
    }
})
[ordered]@{
    events = $events
    log_oldest_at = $oldest.TimeCreated.ToUniversalTime().ToString('o')
    log_reset = [bool]$reset
} | ConvertTo-Json -Depth 5 -Compress
} catch {
    $code = 'read_failed'
    if ($_.FullyQualifiedErrorId -match 'LogInfoUnavailable|NoMatchingLogsFound') { $code = 'log_unavailable' }
    $exception = $_.Exception
    while ($null -ne $exception) {
        if ($exception -is [System.UnauthorizedAccessException] -or
            $exception.HResult -eq -2147024891 -or
            $exception.NativeErrorCode -eq 5) {
            $code = 'access_denied'
            break
        }
        $exception = $exception.InnerException
    }
    @{ collection_error = $code; error_id = $_.FullyQualifiedErrorId } | ConvertTo-Json -Compress
}
""".replace("SINCE", stamp).replace("AFTER_RECORD", str(int(after_record))).replace("LIMIT", str(EVENT_LIMIT + 1)).replace("ANCHOR", anchor)


def normalize_event(row: dict[str, Any]) -> dict[str, Any]:
    """Allowlist excludes command lines, user names, paths and network addresses."""
    event_id = int(row["event_id"])
    if event_id not in (1, 5, 25, 255):
        raise ValueError("Unsupported Sysmon event")
    occurred = datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00"))
    if occurred.tzinfo is None:
        raise ValueError("Event time must include timezone")
    return {
        "event_id": event_id,
        "record_id": int(row["record_id"]),
        "occurred_at": occurred.astimezone(timezone.utc).isoformat(),
        "process_guid": row.get("process_guid") or None,
        "process_id": int(row["process_id"]) if row.get("process_id") else None,
        "image": PureWindowsPath(row.get("image") or "").name or None,
        "parent_process_guid": row.get("parent_process_guid") or None,
        "parent_image": PureWindowsPath(row.get("parent_image") or "").name or None,
    }


@register
class SecurityCollector(Collector):
    name = "security"
    milestone = "M5"
    description = "동의 후 Sysmon 프로세스 시작/종료·변조·수집 오류 이벤트"

    def __init__(self, consent: bool = False, since: datetime | None = None):
        self.consent = consent
        self.consent_at = datetime.now(timezone.utc)
        self.since = since or self.consent_at - timedelta(hours=1)
        self.after_record = 0
        self.anchor_time = None
        self.failure_code = None

    def available(self):
        if not self.consent:
            return False, "프로세스 이력 수집 동의가 필요합니다 (--security-consent)"
        return super().available()

    def collect(self) -> dict[str, Any]:
        self.failure_code = None
        if not self.consent:
            raise PermissionError("Sysmon collection requires consent")
        raw = json.loads(run_powershell(build_script(self.since, self.after_record, self.anchor_time)))
        if raw.get("collection_error"):
            self.failure_code = raw["collection_error"]
            messages = {
                "access_denied": "Sysmon 로그 읽기 권한이 없습니다. PowerShell을 '관리자 권한으로 실행'한 뒤 다시 시도하세요. 이미 관리자라면 로그 접근 정책을 확인하세요. --security-consent는 Windows 권한을 부여하지 않습니다.",
                "log_unavailable": "Sysmon 로그 정보를 읽을 수 없습니다. 관리자 PowerShell에서 로그 접근 권한과 Sysmon 설치 상태를 확인하세요.",
                "log_disabled": "Sysmon 로그가 비활성화되어 있습니다. Sysmon 로그 설정을 확인하세요.",
            }
            raise CimError(messages.get(self.failure_code, "Sysmon 이벤트 조회 실패: " + str(raw.get("error_id", "unknown"))))
        rows = raw.get("events") or []
        events = [normalize_event(row) for row in rows[:EVENT_LIMIT]]
        oldest = datetime.fromisoformat(raw["log_oldest_at"].replace("Z", "+00:00"))
        truncated = len(rows) > EVENT_LIMIT
        gap = bool(raw.get("log_reset")) or oldest > self.since
        return {
            "consent": {"version": "sysmon-minimal-v1", "granted_at": self.consent_at.isoformat()},
            "window_start": self.since.isoformat(),
            "window_end": datetime.now(timezone.utc).isoformat(),
            "events": events,
            "truncated": truncated,
            "log_gap": gap,
            "log_reset": bool(raw.get("log_reset")),
            "log_oldest_at": raw["log_oldest_at"],
            "_partial": truncated or gap or any(e["event_id"] == 255 for e in events),
        }

    def acknowledge(self, data: dict[str, Any]) -> None:
        """Advance only AFTER the corresponding snapshot is durably saved."""
        events = data.get("events") or []
        if events:
            self.after_record = events[-1]["record_id"]
            self.anchor_time = events[-1]["occurred_at"]
        elif data.get("log_reset"):
            self.after_record = 0
            self.anchor_time = None
