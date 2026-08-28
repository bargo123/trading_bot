@echo off
setlocal
set "REPO=%~dp0"
start "AEGIS Firehose Diagnostics" cmd /k ""%REPO%.venv\Scripts\python.exe" "%REPO%bot\scripts\watch_firehose_live.py" --config "%REPO%bot\config_mt5_demo_firehose_hw.yaml" %*"
endlocal
