"""M5 security collector: bounded Sysmon aggregates and platform protection state."""

from __future__ import annotations

import json
import os
from typing import Any

from ..win import cim, events
from .base import Collector, register

_STATE_SCRIPT = r"""
$result = @{}
try { $d = Get-CimInstance -Namespace root/microsoft/windows/defender -ClassName MSFT_MpComputerStatus; $result.defender = @{antivirus_enabled=[bool]$d.AntivirusEnabled; realtime_enabled=[bool]$d.RealTimeProtectionEnabled} } catch { $result.defender=$null }
try { $t = Get-CimInstance -Namespace root/cimv2/security/microsofttpm -ClassName Win32_Tpm; $result.tpm_enabled=if ($null -ne $t) {[bool]$t.IsEnabled_InitialValue} else {$null} } catch { $result.tpm_enabled=$null }
try { $result.secure_boot=[bool](Confirm-SecureBootUEFI) } catch { $result.secure_boot=$null }
$result | ConvertTo-Json -Depth 3 -Compress
"""


@register
class SecurityCollector(Collector):
    name = "security"
    milestone = "M5"
    description = "Sysmon 집계 / Defender / TPM / Secure Boot"

    def collect(self) -> dict[str, Any]:
        state = self._security_state()
        setup: dict[str, Any] | None = None
        try:
            result = events.query_events()
            if result.get("status") == "skipped" and os.environ.get("SPECCHECK_SYSMON_AUTO_SETUP") == "1":
                setup = events.provision_sysmon()
                if setup.get("status") == "ready":
                    result = events.query_events()
                else:
                    result = {"status": "skipped", "reason": setup.get("reason", "sysmon_setup_failed"), "events": []}
            sysmon = {"status": result.get("status", "skipped"), **events.aggregate(result)}
            if result.get("reason"):
                sysmon["reason"] = result["reason"]
        except cim.CimError:
            sysmon = {"status": "skipped", "reason": "event_log_unavailable_or_access_denied"}
        if sysmon["status"] == "skipped":
            sysmon.setdefault("reason", "Sysmon 로그를 읽지 못했습니다. 설치 및 이벤트 로그 권한을 확인하세요.")
        if setup is not None:
            sysmon["setup_status"] = setup.get("status", "skipped")

        defender = state.get("defender") or {}
        incomplete = (
            sysmon["status"] != "ok"
            or bool(sysmon.get("truncated"))
            or any(state.get(key) is None for key in ("tpm_enabled", "secure_boot"))
            or any(defender.get(key) is None for key in ("antivirus_enabled", "realtime_enabled"))
        )
        return {"sysmon": sysmon, "security_state": state, "_partial": incomplete}

    @staticmethod
    def _security_state() -> dict[str, Any]:
        try:
            raw = json.loads(cim.run_powershell(_STATE_SCRIPT, timeout=10).lstrip("\ufeff"))
        except (cim.CimError, ValueError, TypeError, AttributeError):
            raw = {}
        defender = raw.get("defender") or {}
        return {
            "defender": {
                key: defender.get(key) if isinstance(defender.get(key), bool) else None
                for key in ("antivirus_enabled", "realtime_enabled")
            },
            **{
                key: raw.get(key) if isinstance(raw.get(key), bool) else None
                for key in ("tpm_enabled", "secure_boot")
            },
        }
