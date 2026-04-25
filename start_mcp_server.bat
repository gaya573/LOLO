@echo off
setlocal
cd /d "%~dp0"
echo Local Compute MCP server starting...
echo Keep this window open while your MCP client is connected.
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m local_compute_mcp.server --config "%~dp0workers.yaml"
pause
