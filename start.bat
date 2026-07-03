@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set "PYBASE="
for %%C in ("py -3" "python" "python3") do (
  if not defined PYBASE (
    %%~C -c "import tkinter" >nul 2>nul
    if !errorlevel! equ 0 set "PYBASE=%%~C"
  )
)
if not defined PYBASE (
  echo [X] Python 3.8+ with tkinter not found. Run install.bat first,
  echo     or install Python from https://www.python.org/downloads/
  pause
  goto :eof
)

REM Launch without a console window when possible.
where pyw >nul 2>nul && ( start "" pyw "%~dp0run.pyw" & goto :eof )
where pythonw >nul 2>nul && ( start "" pythonw "%~dp0run.pyw" & goto :eof )
start "" %PYBASE% "%~dp0run.pyw"
goto :eof
