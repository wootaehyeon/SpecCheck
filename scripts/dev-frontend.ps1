# 정적 프론트엔드 서버 (http://127.0.0.1:5599)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
python -m http.server 5599 --directory (Join-Path $root 'frontend/web')
