@echo off
echo ========================================
echo   Midas Frontend WebSocket Server
echo ========================================
echo.
echo Starting standalone WebSocket server on port 8001...
echo.

REM Start frontend WebSocket server in new window
start "Midas Frontend WS" cmd /k "cd /d %~dp0 && python ws_frontend_server.py"

echo.
echo ========================================
echo   Frontend WebSocket Server Started!
echo ========================================
echo   Connect to: ws://127.0.0.1:8001
echo ========================================
echo.
echo Press any key to exit this window...
pause >nul
