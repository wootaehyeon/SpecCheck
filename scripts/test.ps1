# 전체 테스트 (agent + backend)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$failed = $false

Write-Host "`n=== agent ===" -ForegroundColor Cyan
Set-Location (Join-Path $root 'agent')
python -m pytest -q
if ($LASTEXITCODE -ne 0) { $failed = $true }

Write-Host "`n=== backend ===" -ForegroundColor Cyan
Set-Location (Join-Path $root 'backend')
python -m pytest -q
if ($LASTEXITCODE -ne 0) { $failed = $true }

Set-Location $root
if ($failed) { exit 1 }
Write-Host "`n전체 통과" -ForegroundColor Green
