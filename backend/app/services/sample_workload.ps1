$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$clock = [Diagnostics.Stopwatch]::StartNew()
function Read-Sample {
    $cpu = Get-CimInstance Win32_PerfRawData_PerfOS_Processor -Filter "Name='_Total'"
    $memory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    $disks = @(Get-CimInstance Win32_PerfRawData_PerfDisk_PhysicalDisk -ErrorAction SilentlyContinue |
        Where-Object Name -ne '_Total' |
        Select-Object Name,Frequency_PerfTime,AvgDisksecPerRead,AvgDisksecPerRead_Base,AvgDisksecPerWrite,AvgDisksecPerWrite_Base)
    $apps = @(Get-CimInstance Win32_PerfRawData_PerfProc_Process |
        Where-Object { $_.IDProcess -gt 4 } |
        Select-Object Name,IDProcess,ElapsedTime,PercentProcessorTime,WorkingSetPrivate,IODataBytesPersec)
    [pscustomobject]@{
        t = $clock.Elapsed.TotalSeconds
        cpu = $cpu.PercentProcessorTime
        ticks = $cpu.Timestamp_Sys100NS
        available = $memory.AvailableMBytes
        pages = $memory.PagesInputPersec
        disks = $disks
        apps = $apps
    }
}
$os = Get-CimInstance Win32_OperatingSystem
$cores = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
$first = Read-Sample
$samples = @($first)
while ($samples[-1].t - $first.t -lt 30) {
    Start-Sleep -Milliseconds 1500
    $samples += Read-Sample
}
@{samples=$samples; cores=$cores; memoryMB=$os.TotalVisibleMemorySize / 1024} | ConvertTo-Json -Depth 4 -Compress
