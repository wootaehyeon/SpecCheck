@echo off
setlocal
cd /d "%~dp0"
if not exist "speccheck-monitor.json" (
  echo Download speccheck-monitor.json from the monitoring page and place it in this folder.
  pause
  exit /b 2
)
echo SpecCheck sends hardware, usage and top-process names to your configured server.
echo If enabled in your config, it also sends Sysmon process events. Admin rights are required for Sysmon.
echo Press Ctrl+C to stop. Cloud history is kept for 7 days. Local history remains on your PC.
choice /C YN /M "Start the selected collection and server upload?"
if errorlevel 2 exit /b 0
where py >nul 2>nul
if errorlevel 1 (
  python -m speccheck_agent watch --config "speccheck-monitor.json" --consent --security-consent
) else (
  py -3 -m speccheck_agent watch --config "speccheck-monitor.json" --consent --security-consent
)
pause
