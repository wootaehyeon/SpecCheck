# Backend 개발 서버 (http://127.0.0.1:8000, 문서 /docs)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'backend')
python -m uvicorn app.main:app --reload --port 8000
