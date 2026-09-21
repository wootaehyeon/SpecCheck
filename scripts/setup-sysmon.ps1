#Requires -RunAsAdministrator
<#
Installs the Microsoft-signed Sysinternals Sysmon service using the repository
configuration. Existing installations are never overwritten. Sysmon stores raw
events locally in Windows; the agent keeps only anonymized aggregates.
#>
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$packageDir = Join-Path $repoRoot 'agent\var\sysmon'
$configPath = Join-Path $repoRoot 'agent\sysmon-config.xml'
$logPath = Join-Path $repoRoot 'agent\var\sysmon-install.log'
New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
Start-Transcript -Path $logPath -Force | Out-Null
try {
    $installed = @(Get-Service -Name Sysmon,Sysmon64,Sysmon64a -ErrorAction SilentlyContinue)
    if ($installed.Count -gt 0) {
        throw 'Sysmon is already installed. Inspect its service and event log; existing configuration was not changed.'
    }
    if (Test-Path (Join-Path $env:WINDIR 'System32\Sysmon.exe')) {
        throw 'Built-in Sysmon is present. Use the Windows Sysmon installation procedure instead of installing a second version.'
    }
    $binaryName = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'Sysmon64a.exe' } else { 'Sysmon64.exe' }
    $binaryPath = Join-Path $packageDir $binaryName
    if (-not (Test-Path -LiteralPath $binaryPath)) {
        $archivePath = Join-Path $packageDir 'Sysmon.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://download.sysinternals.com/files/Sysmon.zip' -OutFile $archivePath
        Expand-Archive -LiteralPath $archivePath -DestinationPath $packageDir -Force
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $binaryPath
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') {
        throw 'Sysmon must have a valid Microsoft Authenticode signature.'
    }
    [xml]$configDocument = Get-Content -LiteralPath $configPath -Raw
    if ($configDocument.DocumentElement.Name -ne 'Sysmon') { throw 'Invalid Sysmon configuration root.' }
    # Sysmon's native XML loader can reject non-ASCII configuration paths.
    # Stage both files outside Korean OneDrive/Desktop paths before invoking it.
    $installDir = Join-Path $env:ProgramData 'SpecCheck\Sysmon'
    if ($installDir -match '[^\x00-\x7F]') { throw 'An ASCII ProgramData path is required by the Sysmon XML loader.' }
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    $installedBinary = Join-Path $installDir $binaryName
    $installedConfig = Join-Path $installDir 'sysmon-config.xml'
    Copy-Item -LiteralPath $binaryPath -Destination $installedBinary -Force
    Copy-Item -LiteralPath $configPath -Destination $installedConfig -Force
    & $installedBinary -accepteula -i $installedConfig
    if ($LASTEXITCODE -ne 0) { throw "Sysmon installation failed: exit code $LASTEXITCODE" }
    $service = Get-Service -Name ($binaryName -replace '\.exe$', '')
    $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    $channel = Get-WinEvent -ListLog 'Microsoft-Windows-Sysmon/Operational' -ErrorAction Stop
    if (-not $channel.IsEnabled) { throw 'Installation completed but the Sysmon event channel is disabled.' }
    Write-Output 'Sysmon installed; service running; event log enabled.'
} catch {
    Write-Output $_.Exception.Message
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
