@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Removing auto-start entry...
where py >nul 2>nul && (py -3 -m claude_usage_monitor --uninstall-autostart & goto :eof)
where python >nul 2>nul && (python -m claude_usage_monitor --uninstall-autostart & goto :eof)
echo [!] Python not found.
pause
