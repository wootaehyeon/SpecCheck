# Start/stop the local Windows Agent connected through agent/speccheck-monitor.json.
param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Start',
    [switch]$Consent,
    [switch]$SecurityConsent,
    [switch]$ElevatedChild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$agentDir = Join-Path $root 'agent'
$stateDir = Join-Path $root '.speccheck'
$stateFile = Join-Path $stateDir 'monitor-process.json'
$configFile = Join-Path $agentDir 'speccheck-monitor.json'

# Match the process creation time as well as PID to avoid stopping a reused PID.
$running = $null
if (Test-Path -LiteralPath $stateFile) {
    $saved = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
    $candidate = Get-Process -Id $saved.process_id -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.StartTime.ToUniversalTime().Ticks -eq $saved.started_ticks) {
        $running = $candidate
    }
}

$needsAdmin = $SecurityConsent -or ($Action -eq 'Stop' -and $running -and $saved.security_enabled)
if ($needsAdmin) {
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        if ($ElevatedChild) { throw 'Administrator rights are required for Sysmon.' }
        $arguments = '-NoProfile -File "' + $PSCommandPath + '" -Action ' + $Action + ' -ElevatedChild'
        if ($Consent) { $arguments += ' -Consent' }
        if ($SecurityConsent) { $arguments += ' -SecurityConsent' }
        try {
            Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -ErrorAction Stop | Out-Null
            Write-Output 'Approve the Windows UAC prompt for this Sysmon Agent action. Check -Action Status and the Agent logs afterwards.'
        } catch {
            throw 'Windows administrator approval was cancelled. The Sysmon Agent action was not performed.'
        }
        return
    }
}

if ($Action -eq 'Stop') {
    if ($running) { Stop-Process -Id $running.Id -ErrorAction Stop }
    if (Test-Path -LiteralPath $stateFile) { Remove-Item -LiteralPath $stateFile }
    Write-Output 'SpecCheck background monitoring stopped. Stored history is retained.'
    return
}

if ($Action -eq 'Status' -or $running) {
    if ($running) { Write-Output ('SpecCheck monitoring is running (PID ' + $running.Id + '; Sysmon: ' + [bool]$saved.security_enabled + ').') }
    else { Write-Output 'SpecCheck background monitoring is stopped.' }
    return
}

if (-not $Consent) {
    throw 'Use -Consent to allow collection and upload. Add -SecurityConsent only to enable the Sysmon collection allowed in your connection file.'
}
if (-not (Test-Path -LiteralPath $configFile)) {
    throw 'Download speccheck-monitor.json from your monitoring page and put it in the agent folder.'
}

if ($SecurityConsent) {
    $connection = Get-Content -Raw -LiteralPath $configFile -Encoding UTF8 | ConvertFrom-Json
    if (-not $connection.security_consent) {
        throw 'Enable Sysmon on your monitoring page and replace speccheck-monitor.json before starting with -SecurityConsent.'
    }
}

$python = if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -c 'import sys; print(sys.executable)'
} else {
    & python -c 'import sys; print(sys.executable)'
}
if ($LASTEXITCODE -ne 0 -or -not $python) { throw 'Python 3.12 is required to start this Agent.' }
$python = $python.Trim()
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$previousHome = $env:SPECCHECK_AGENT_HOME
try {
    $env:SPECCHECK_AGENT_HOME = $stateDir
    $agentArguments = @('-u', '-m', 'speccheck_agent', 'watch', '--config', 'speccheck-monitor.json', '--consent')
    if ($SecurityConsent) { $agentArguments += '--security-consent' }
    $process = Start-Process -FilePath $python -WindowStyle Hidden -PassThru `
        -ArgumentList $agentArguments `
        -WorkingDirectory $agentDir `
        -RedirectStandardOutput (Join-Path $stateDir 'monitor.stdout.log') `
        -RedirectStandardError (Join-Path $stateDir 'monitor.stderr.log')
    @{ process_id = $process.Id; started_ticks = $process.StartTime.ToUniversalTime().Ticks; security_enabled = [bool]$SecurityConsent } |
        ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
} finally {
    $env:SPECCHECK_AGENT_HOME = $previousHome
}
Write-Output ('SpecCheck monitoring started (PID ' + $process.Id + ').')
Write-Output 'Stop: .\scripts\monitor.ps1 -Action Stop'
Write-Output 'Logs: .speccheck\monitor.stdout.log and monitor.stderr.log'
