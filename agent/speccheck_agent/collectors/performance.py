"""Sample CPU/memory/disk counters three times in one PowerShell process."""
import json
from .base import Collector, register
from ..win import cim

SCRIPT = r"""
$samples = @(1..3 | ForEach-Object {
    $r = @{timestamp=[DateTime]::UtcNow.ToString('o')}
    try { $c = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"; $r.cpu_percent=[double]$c.PercentProcessorTime } catch {}
    try { $m = Get-CimInstance Win32_OperatingSystem; if ($m.TotalVisibleMemorySize -gt 0) { $r.memory_percent=100*(1-$m.FreePhysicalMemory/$m.TotalVisibleMemorySize) } } catch {}
    try { $d = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'"; $r.disk_queue=[double]$d.AvgDiskQueueLength } catch {}
    $r
    if ($_ -lt 3) { Start-Sleep -Milliseconds 500 }
})
@{samples=$samples} | ConvertTo-Json -Depth 4 -Compress
"""

@register
class PerformanceCollector(Collector):
    name = 'performance'
    milestone = 'M2'
    description = 'CPU / memory / disk sampling'

    def collect(self):
        data = json.loads(cim.run_powershell(SCRIPT, timeout=12).lstrip('\ufeff'))
        samples = data.get('samples', [])
        summary = {}
        for key in ('cpu_percent', 'memory_percent', 'disk_queue'):
            values = [s[key] for s in samples if isinstance(s.get(key), (int, float))]
            summary[key] = {'mean': sum(values)/len(values), 'max': max(values)} if values else None
        return {'samples': samples, 'summary': summary,
                '_skipped': not any(summary.values()),
                '_reason': 'Performance counters unavailable; check CIM read permissions' if not any(summary.values()) else None,
                '_partial': len(samples) < 3 or any(len([s for s in samples if k in s]) < 3 for k in summary)}
