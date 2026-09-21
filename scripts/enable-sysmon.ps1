<#
  Enables the Sysmon telemetry required by SpecCheck M5.
  Run from an elevated PowerShell session. The script prefers the Windows
  optional feature and falls back to the official Sysinternals package.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $ConfigPath = Join-Path $scriptDir '..\agent\sysmon-config.xml'
}
$setupDir = Join-Path $env:ProgramData 'SpecCheck\Sysmon'
$setupLog = Join-Path $setupDir 'setup-error.txt'
New-Item -ItemType Directory -Path $setupDir -Force | Out-Null
trap {
    ($_ | Out-String) | Set-Content -LiteralPath $setupLog -Encoding utf8
    exit 1
}

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    throw 'Administrator privileges are required to install or configure Sysmon.'
}

$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$sysmon = Get-Command sysmon, sysmon64 -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $sysmon) {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName Sysmon -ErrorAction SilentlyContinue
    if ($feature -and $feature.State -ne 'Enabled') {
        $featureResult = Enable-WindowsOptionalFeature -Online -FeatureName Sysmon -All -NoRestart
        if ($featureResult.RestartNeeded) {
            [pscustomobject]@{ status = 'restart_required'; feature = 'Sysmon' } | ConvertTo-Json -Compress
            exit 0
        }
    }
    $sysmon = Get-Command sysmon, sysmon64 -ErrorAction SilentlyContinue | Select-Object -First 1
}

if (-not $sysmon) {
    $installDir = $setupDir
    $archive = Join-Path $env:TEMP 'SpecCheck-Sysmon.zip'
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Invoke-WebRequest -Uri 'https://download.sysinternals.com/files/Sysmon.zip' -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $installDir -Force
    $binary = Join-Path $installDir 'Sysmon64.exe'
    if (-not (Test-Path -LiteralPath $binary)) {
        throw 'The official Sysmon package did not contain Sysmon64.exe.'
    }
    $sysmon = Get-Command $binary
}
$sysmonPath = if ($sysmon.Path) { $sysmon.Path } else { $sysmon.Source }
if (-not $sysmonPath) {
    throw 'Sysmon executable path could not be resolved.'
}

$service = Get-Service -Name 'Sysmon', 'Sysmon64' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($service) {
    & $sysmonPath -c $resolvedConfig
} else {
    & $sysmonPath -accepteula -i $resolvedConfig
}
if ($LASTEXITCODE -ne 0) {
    throw "Sysmon returned exit code $LASTEXITCODE."
}

$log = Get-WinEvent -ListLog 'Microsoft-Windows-Sysmon/Operational' -ErrorAction Stop
[pscustomobject]@{
    status = 'ready'
    source = $sysmonPath
    channel = 'Microsoft-Windows-Sysmon/Operational'
    enabled = [bool]$log.IsEnabled
    recordCount = [int64]$log.RecordCount
} | ConvertTo-Json -Compress
