@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title SpecCheck Local Launcher

echo.
echo ========================================
echo   SpecCheck one-click local launcher
echo ========================================
echo.

if not exist "package.json" (
  echo [ERROR] package.json was not found.
  echo Keep this BAT file in the SpecCheck project root.
  goto :fail
)

rem start:local verifies project identity and readiness before opening a browser.
rem Never terminate a process using only a stale development lock PID.

set "NODE_EXE="
if exist "%CD%\.tools\node-v22.23.0-win-x64\node.exe" set "NODE_EXE=%CD%\.tools\node-v22.23.0-win-x64\node.exe"
for /f "delims=" %%I in ('where node.exe 2^>nul') do if not defined NODE_EXE set "NODE_EXE=%%I"
if not defined NODE_EXE if exist "%ProgramFiles%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles%\nodejs\node.exe"
if not defined NODE_EXE if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "NODE_EXE=%LOCALAPPDATA%\Programs\nodejs\node.exe"
if not defined NODE_EXE if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" set "NODE_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

if not defined NODE_EXE (
  echo [ERROR] Node.js was not found.
  echo Install Node.js 22.13 or newer, then run this file again.
  goto :fail
)

"%NODE_EXE%" -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>22||(a===22&&b>=13)?0:1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js 22.13 or newer is required.
  "%NODE_EXE%" --version
  goto :fail
)

for %%I in ("%NODE_EXE%") do set "PATH=%%~dpI;%PATH%"

set "PNPM_KIND="
set "PNPM_CMD="
for /f "delims=" %%I in ('where pnpm.cmd 2^>nul') do if not defined PNPM_CMD set "PNPM_CMD=%%I"
if defined PNPM_CMD set "PNPM_KIND=direct"

if not defined PNPM_KIND if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd" (
  set "PNPM_KIND=direct"
  set "PNPM_CMD=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
)

if not defined PNPM_KIND (
  for /f "delims=" %%I in ('where corepack.cmd 2^>nul') do if not defined PNPM_CMD set "PNPM_CMD=%%I"
  if defined PNPM_CMD set "PNPM_KIND=corepack"
)

if not defined PNPM_KIND (
  for /f "delims=" %%I in ('where npx.cmd 2^>nul') do if not defined PNPM_CMD set "PNPM_CMD=%%I"
  if defined PNPM_CMD set "PNPM_KIND=npx"
)

if not defined PNPM_KIND (
  echo [ERROR] pnpm, Corepack, or npx was not found.
  echo Reinstall Node.js with npm included, then run this file again.
  goto :fail
)

echo [1/3] Preparing web packages...
if "%PNPM_KIND%"=="direct" call "%PNPM_CMD%" install --frozen-lockfile
if "%PNPM_KIND%"=="corepack" call "%PNPM_CMD%" pnpm install --frozen-lockfile
if "%PNPM_KIND%"=="npx" call "%PNPM_CMD%" --yes pnpm@11.19.0 install --frozen-lockfile
if errorlevel 1 (
  echo [ERROR] Web package installation failed.
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo [2/3] Creating the private Python environment...
  where py.exe >nul 2>nul
  if not errorlevel 1 py -3 -m venv .venv

  if not exist ".venv\Scripts\python.exe" (
    where python.exe >nul 2>nul
    if not errorlevel 1 python -m venv .venv
  )

  if not exist ".venv\Scripts\python.exe" if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv .venv
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python 3 was not found or the virtual environment could not be created.
  echo Install Python 3.10 or newer, then run this file again.
  goto :fail
)

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  ".venv\Scripts\python.exe" --version
  goto :fail
)

set "INSTALL_PYTHON_DEPS=1"
if exist ".venv\.requirements-installed.txt" (
  fc /b "backend\requirements.txt" ".venv\.requirements-installed.txt" >nul 2>nul
  if not errorlevel 1 set "INSTALL_PYTHON_DEPS=0"
)

if "%INSTALL_PYTHON_DEPS%"=="1" (
  echo [2/3] Installing backend packages. The first run may take several minutes...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "backend\requirements.txt"
  if errorlevel 1 (
    echo [ERROR] Backend package installation failed.
    goto :fail
  )
  copy /y "backend\requirements.txt" ".venv\.requirements-installed.txt" >nul
) else (
  echo [2/3] Backend packages are ready.
)

set "SPECCHECK_PYTHON=%CD%\.venv\Scripts\python.exe"

echo [3/3] Starting SpecCheck...
echo The browser will open automatically when the UI is ready.
echo Keep this window open. Press Ctrl+C to stop SpecCheck.
echo.

if "%PNPM_KIND%"=="direct" call "%PNPM_CMD%" start:local
if "%PNPM_KIND%"=="corepack" call "%PNPM_CMD%" pnpm start:local
if "%PNPM_KIND%"=="npx" call "%PNPM_CMD%" --yes pnpm@11.19.0 start:local
set "DEV_EXIT=%ERRORLEVEL%"

if not "%DEV_EXIT%"=="0" (
  echo [ERROR] SpecCheck did not start. See the message above.
  goto :fail
)

echo.
echo SpecCheck has stopped.
pause
exit /b 0

:fail
echo.
echo Setup did not complete. Review the message above and try again.
pause
exit /b 1
