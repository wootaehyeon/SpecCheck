"""Volume free space and storage wear. Unsupported counters stay missing.

Disk numbers are local join keys, not serials. SMART vendor blobs and volume
labels are never stored. Reallocated sectors are unavailable in this adapter.
"""
import json
from .base import Collector, register
from ..win import cim

SCRIPT = r"""
$r = @{volumes=@(); disks=@(); partial=$false}
try {
    $r.volumes = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        if ($_.Size -gt 0) { @{volume=$_.DeviceID; is_system=($_.DeviceID -eq $env:SystemDrive); free_percent=(100*$_.FreeSpace/$_.Size)} }
    })
} catch { $r.partial=$true }
try {
    $r.disks = @(Get-PhysicalDisk | ForEach-Object {
        $row = @{disk_id=[string]$_.DeviceId; wear_percent=$null; reallocated_sectors=$null}
        try { $c = $_ | Get-StorageReliabilityCounter -ErrorAction Stop; if ($null -ne $c.Wear) { $row.wear_percent=[double]$c.Wear } else { $r.partial=$true } } catch { $r.partial=$true }
        $row
    })
} catch { $r.partial=$true }
$r | ConvertTo-Json -Depth 4 -Compress
"""

@register
class StorageHealthCollector(Collector):
    name = 'storage_health'
    milestone = 'M2'
    description = 'Volume free space / storage wear'

    def collect(self):
        raw = json.loads(cim.run_powershell(SCRIPT, timeout=12).lstrip('\ufeff'))
        return {'volumes': raw.get('volumes', []), 'disks': raw.get('disks', []),
                '_skipped': not raw.get('volumes') and not raw.get('disks'),
                '_reason': 'Storage counters unavailable; check CIM read permissions' if not raw.get('volumes') and not raw.get('disks') else None,
                '_partial': bool(raw.get('partial')) or not raw.get('volumes')}
