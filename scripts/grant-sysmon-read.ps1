#Requires -RunAsAdministrator
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^S-1-5-21-\d+-\d+-\d+-\d+$')]
    [string]$UserSid
)

# Add read (0x1) for one local/domain user to this channel only. Preserve all
# existing access entries, owner, group and audit settings. No group membership
# changes or write/clear permissions are granted.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$logPath = Join-Path $repoRoot 'agent\var\sysmon-permissions.log'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null
Start-Transcript -Path $logPath -Force | Out-Null
$channel = $null
try {
    $sid = [System.Security.Principal.SecurityIdentifier]::new($UserSid)
    $channel = [System.Diagnostics.Eventing.Reader.EventLogConfiguration]::new('Microsoft-Windows-Sysmon/Operational')
    $original = $channel.SecurityDescriptor
    $descriptor = [System.Security.AccessControl.RawSecurityDescriptor]::new($original)
    if ($null -eq $descriptor.DiscretionaryAcl) { throw 'Unexpected empty channel ACL; no changes made.' }
    $exists = @($descriptor.DiscretionaryAcl | Where-Object {
        $_ -is [System.Security.AccessControl.CommonAce] -and
        $_.AceQualifier -eq [System.Security.AccessControl.AceQualifier]::AccessAllowed -and
        $_.SecurityIdentifier -eq $sid -and ($_.AccessMask -band 1) -eq 1
    }).Count -gt 0
    if (-not $exists) {
        $backupDir = Join-Path $env:ProgramData 'SpecCheck\Sysmon'
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        $backupPath = Join-Path $backupDir 'channel-access-before.sddl'
        if (-not (Test-Path -LiteralPath $backupPath)) {
            Set-Content -LiteralPath $backupPath -Value $original -Encoding ASCII
        }
        $ace = [System.Security.AccessControl.CommonAce]::new(
            [System.Security.AccessControl.AceFlags]::None,
            [System.Security.AccessControl.AceQualifier]::AccessAllowed,
            1, $sid, $false, $null)
        $descriptor.DiscretionaryAcl.InsertAce($descriptor.DiscretionaryAcl.Count, $ace)
        $channel.SecurityDescriptor = $descriptor.GetSddlForm([System.Security.AccessControl.AccessControlSections]::All)
        $channel.SaveChanges()
    }
    Write-Output 'Sysmon channel read permission is configured for the requested user.'
} catch {
    Write-Output $_.Exception.Message
    exit 1
} finally {
    if ($null -ne $channel) { $channel.Dispose() }
    Stop-Transcript | Out-Null
}
