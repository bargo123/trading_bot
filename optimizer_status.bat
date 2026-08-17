@echo off
setlocal
echo Running optimizer status...
set "BOT=%~dp0bot"
if not exist "%BOT%\.venv\Scripts\python.exe" (
  echo Missing venv: %BOT%\.venv\Scripts\python.exe
  echo Create it with: cd /d "%BOT%" ^& python -m venv .venv ^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
set PYTHONUNBUFFERED=1
"%BOT%\.venv\Scripts\python.exe" -u "%BOT%\scripts\optimizer_status.py" %*
echo.
echo Exit code %ERRORLEVEL%
exit /b %ERRORLEVEL%
