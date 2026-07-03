@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set "PYBASE="
for %%C in ("py -3" "python" "python3") do (
  if not defined PYBASE (
    %%~C --version >nul 2>nul
    if !errorlevel! equ 0 set "PYBASE=%%~C"
  )
)
if not defined PYBASE (
  echo [X] Python not found on PATH.
  pause
  goto :eof
)

echo Removing the auto-start entry...
%PYBASE% -m claude_usage_monitor --uninstall-autostart
echo.
pause
goto :eof
