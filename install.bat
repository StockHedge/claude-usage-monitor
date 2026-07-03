@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ==================================================
echo   Claude 5h Usage Monitor - Setup
echo ==================================================
echo   Folder: %CD%
echo.

REM --- 1) Find a Python interpreter on PATH ---
set "PYBASE="
for %%C in ("py -3" "python" "python3") do (
  if not defined PYBASE (
    %%~C --version >nul 2>nul
    if !errorlevel! equ 0 set "PYBASE=%%~C"
  )
)
if not defined PYBASE (
  echo [X] Python was not found on PATH.
  echo     Install Python 3.8+ from https://www.python.org/downloads/
  echo     and CHECK "Add python.exe to PATH" during installation.
  echo.
  pause
  goto :eof
)
for /f "delims=" %%V in ('%PYBASE% --version 2^>^&1') do echo Found: %%V   ^(%PYBASE%^)

REM --- 2) Verify tkinter (required for the popup UI) ---
%PYBASE% -c "import tkinter" >nul 2>nul
if !errorlevel! neq 0 (
  echo.
  echo [X] Python is installed but the "tkinter" module is missing.
  echo     Re-install Python from python.org and make sure the
  echo     "tcl/tk and IDLE" option is CHECKED during installation.
  echo.
  pause
  goto :eof
)
echo tkinter: OK

REM --- 3) Verify the package imports from this folder ---
%PYBASE% -c "import claude_usage_monitor" >nul 2>nul
if !errorlevel! neq 0 (
  echo.
  echo [X] Could not import "claude_usage_monitor" from this folder.
  echo     install.bat must sit next to the claude_usage_monitor folder.
  echo.
  pause
  goto :eof
)
echo package: OK
echo.

REM --- 4) Launch the setup window ---
echo Opening the setup window (pick your plan, then "Install and start")...
%PYBASE% -m claude_usage_monitor --setup
echo.
echo Done (exit code !errorlevel!).
echo If the popup did not appear, copy any messages above and send them over.
pause
goto :eof
