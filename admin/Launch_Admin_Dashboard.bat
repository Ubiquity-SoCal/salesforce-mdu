@echo off
cd /d "%~dp0"
pip install flask >nul 2>&1
start "Admin Dashboard Server" python admin/admin_server.py
timeout /t 2 /nobreak >nul
start "" http://localhost:5050
echo.
echo Admin Dashboard server is running.
echo Close this window to stop the server.
pause >nul
