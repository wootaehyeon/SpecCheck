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
rem A launcher can exist without a registered Python installation.
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto use_python
echo Python 3.10 or later was not found. Install Python and enable Add python.exe to PATH.
pause
exit /b 3

:use_py
py -3 -m speccheck_agent watch --config "speccheck-monitor.json" --consent --security-consent
goto finished

:use_python
python -m speccheck_agent watch --config "speccheck-monitor.json" --consent --security-consent

:finished
pause
