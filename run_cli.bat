@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m local_compute_mcp.cli --config "%~dp0workers.yaml" %*
