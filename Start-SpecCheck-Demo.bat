@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title SpecCheck Recommendation Demo

echo.
echo ========================================
echo   SpecCheck component recommendation demo
echo ========================================
echo.

if not exist "Start-SpecCheck.bat" (
  echo [ERROR] Start-SpecCheck.bat was not found.
  echo Keep both BAT files in the SpecCheck project root.
  goto :fail
)

if not exist "demo\recommendation-snapshot.json" (
  echo [ERROR] The demo snapshot was not found.
  goto :fail
)

powershell.exe -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($response.StatusCode -lt 500) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo [1/3] Starting SpecCheck in a separate window...
  set "SPECCHECK_NO_BROWSER=1"
  start "SpecCheck Server" "%~dp0Start-SpecCheck.bat"
  set "SPECCHECK_NO_BROWSER="
) else (
  echo [1/3] SpecCheck server is already running.
)

echo [2/3] Waiting for the UI and backend...
powershell.exe -NoProfile -Command "$deadline = (Get-Date).AddMinutes(5); do { try { $ui = Invoke-WebRequest -UseBasicParsing 'http://localhost:3000/' -TimeoutSec 2; $api = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($ui.StatusCode -lt 500 -and $api.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
  echo [ERROR] SpecCheck did not become ready within five minutes.
  goto :fail
)

echo [3/3] Loading the component recommendation demo...
powershell.exe -NoProfile -Command "$snapshot = Get-Content -Raw -Encoding UTF8 'demo\recommendation-snapshot.json' | ConvertFrom-Json; $snapshot.snapshot_id = [guid]::NewGuid().ToString(); $snapshot.collected_at = [DateTimeOffset]::UtcNow.ToString('o'); $body = @{ snapshot = $snapshot } | ConvertTo-Json -Depth 100 -Compress; try { $result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/scans' -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 120; $count = @($result.recommendations).Count; if ($count -lt 1) { throw 'The diagnosis did not create a recommendation.' }; Write-Host ('[OK] Demo diagnosis created: ' + $count + ' recommendation group(s).'); exit 0 } catch { Write-Host ('[ERROR] ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto :fail

start "" "http://localhost:3000/?demo=recommendation"
echo.
echo The demo is ready. Look for memory and storage recommendations.
exit /b 0

:fail
echo.
echo The demo could not be loaded. Review the message above and try again.
pause
exit /b 1
