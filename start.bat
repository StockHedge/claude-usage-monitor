@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw "%~dp0run.pyw" & goto :eof)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0run.pyw" & goto :eof)
where py >nul 2>nul && (start "" py -3 "%~dp0run.pyw" & goto :eof)
echo [!] Python not found. Run install.bat first.
pause
