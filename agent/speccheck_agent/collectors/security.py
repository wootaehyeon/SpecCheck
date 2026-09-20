"""M5: Sysmon minute aggregates and boolean Defender/TPM/Secure Boot state."""
import json
from .base import Collector, register
from ..win import cim, events

STATE_SCRIPT = r"""
$r = @{}
try { $d = Get-CimInstance -Namespace root/microsoft/windows/defender -ClassName MSFT_MpComputerStatus; $r.defender = @{antivirus_enabled=[bool]$d.AntivirusEnabled; realtime_enabled=[bool]$d.RealTimeProtectionEnabled} } catch { $r.defender=$null }
try { $t = Get-CimInstance -Namespace root/cimv2/security/microsofttpm -ClassName Win32_Tpm; if ($null -ne $t) { $r.tpm_enabled=[bool]$t.IsEnabled_InitialValue } else { $r.tpm_enabled=$null } } catch { $r.tpm_enabled=$null }
try { $r.secure_boot=[bool](Confirm-SecureBootUEFI) } catch { $r.secure_boot=$null }
$r | ConvertTo-Json -Depth 3 -Compress
"""

@register
class SecurityCollector(Collector):
    name = 'security'
    milestone = 'M5'
    description = 'Sysmon aggregates / Defender / TPM / Secure Boot'

    def collect(self):
        state = {}
        try:
            raw = json.loads(cim.run_powershell(STATE_SCRIPT, timeout=5).lstrip('\ufeff'))
            defender = raw.get('defender') or {}
            state = {'defender': {k: defender.get(k) if isinstance(defender.get(k), bool) else None
                                  for k in ('antivirus_enabled', 'realtime_enabled')},
                     **{k: raw.get(k) if isinstance(raw.get(k), bool) else None for k in ('tpm_enabled', 'secure_boot')}}
        except (cim.CimError, ValueError, TypeError, AttributeError):
            pass
        try:
            result = events.query_events()
            sysmon = {'status': result.get('status', 'skipped'), **events.aggregate(result)}
        except cim.CimError:
            sysmon = {'status': 'skipped'}
        if sysmon['status'] == 'skipped':
            sysmon['reason'] = 'Sysmon log unavailable; check installation and event-log read permission.'
        incomplete = (sysmon['status'] != 'ok' or sysmon.get('truncated') or sysmon.get('rejected_events')
                      or any(state.get(k) is None for k in ('tpm_enabled', 'secure_boot'))
                      or any(v is None for v in state.get('defender', {'missing': None}).values()))
        return {'sysmon': sysmon, 'security_state': state, '_partial': bool(incomplete)}
