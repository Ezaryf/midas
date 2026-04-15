@echo off
echo ========================================
echo   Midas Trading System - Backend + Bridge
echo ========================================
echo.
echo Starting backend server and MT5 bridge...
echo.

REM Start backend in new window
start "Midas Backend" cmd /k "cd /d %~dp0 && uvicorn main:app --reload --reload-dir app --host 0.0.0.0 --port 8000"

REM Wait for backend to be ready (max 15s)
echo Waiting for backend to start...
set "RETRY_COUNT=0"
:wait_loop
curl -s http://localhost:8000/health >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :backend_ready
set /a RETRY_COUNT+=1
if %RETRY_COUNT% GTR 15 goto :backend_timeout
timeout /t 1 /nobreak >nul
goto :wait_loop

:backend_ready
echo Backend is ready!
echo.

REM Wait a bit more then start MT5 Bridge
timeout /t 2 /nobreak >nul

REM Start MT5 Bridge (auto-trade enabled)
start "Midas MT5 Bridge" cmd /k "cd /d %~dp0 && python mt5_bridge.py --auto-trade"

goto :continue_startup

:backend_timeout
echo WARNING: Backend may not be ready yet
echo Starting bridge anyway...
start "Midas MT5 Bridge" cmd /k "cd /d %~dp0 && python mt5_bridge.py --auto-trade"

:continue_startup
echo.
echo ========================================
echo   All services started!
echo ========================================
echo   Backend:      http://localhost:8000
echo   MT5 Bridge:   Auto-trade ENABLED
echo ========================================
echo.
echo You can close this window.
pause >nul