# Agent 스캔 실행. 인자는 그대로 CLI로 전달된다.
#   .\scripts\scan.ps1                    스캔 후 로컬 저장
#   .\scripts\scan.ps1 --upload           Backend 전송까지
#   .\scripts\scan.ps1 doctor             환경 점검
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'agent')

if ($args.Count -eq 0) {
    python -m speccheck_agent scan
} elseif ($args[0].StartsWith('-')) {
    python -m speccheck_agent scan @args
} else {
    python -m speccheck_agent @args
}
