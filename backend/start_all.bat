@echo off
echo ========================================
echo   Midas Trading System - Full Stack
echo ========================================
echo.
echo Starting backend server and MT5 bridge...
echo.

REM Start backend in new window
start "Midas Backend" cmd /k "cd /d %~dp0 && uvicorn main:app --reload"

REM Wait 3 seconds for backend to start
timeout /t 3 /nobreak >nul

REM Start MT5 bridge in new window (auto-trade enabled)
start "Midas MT5 Bridge" cmd /k "cd /d %~dp0 && python mt5_bridge.py --auto-trade"

echo.
echo ========================================
echo   Both services started!
echo ========================================
echo   Backend: http://localhost:8000
echo   Bridge:  Auto-trade ENABLED
echo ========================================
echo.
echo Press any key to exit this window...
pause >nul
