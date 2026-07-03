@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Claude 5h Usage Monitor - setup
where py >nul 2>nul && (py -3 -m claude_usage_monitor --setup & goto :eof)
where python >nul 2>nul && (python -m claude_usage_monitor --setup & goto :eof)
echo.
echo [!] Python 3.8+ was not found.
echo     Install it from https://www.python.org/downloads/ (check "Add to PATH"),
echo     then run install.bat again.
echo.
pause
