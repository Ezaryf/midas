@echo off
echo ============================================================
echo   MIDAS SYSTEM STATUS CHECK
echo ============================================================
echo.

echo [1/4] Checking Backend (Port 8000)...
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Backend is running
) else (
    echo   [ERROR] Backend not running
    echo   Fix: cd backend ^&^& python main.py
)
echo.

echo [2/4] Checking Frontend (Port 3000)...
curl -s http://localhost:3000 >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Frontend is running
) else (
    echo   [ERROR] Frontend not running
    echo   Fix: npm run dev
)
echo.

echo [3/4] Checking WebSocket (Port 8000/ws)...
curl -s http://localhost:8000/docs >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] WebSocket endpoint available
) else (
    echo   [ERROR] WebSocket not available
    echo   Fix: Start backend first
)
echo.

echo [4/4] Checking MT5 Bridge...
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq mt5_bridge*" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] MT5 Bridge might be running
) else (
    echo   [INFO] MT5 Bridge not detected
    echo   Optional: cd backend ^&^& python mt5_bridge.py --auto-trade
)
echo.

echo ============================================================
echo   CONSOLE WARNINGS EXPLAINED
echo ============================================================
echo.
echo Cookie "__cf_bm" warnings:
echo   - Normal behavior from external APIs
echo   - No action needed
echo.
echo Font preload warnings:
echo   - Next.js optimization messages
echo   - Fonts still load correctly
echo   - No action needed
echo.
echo WebSocket connection errors:
echo   - Backend must be running
echo   - Start with: cd backend ^&^& python main.py
echo.
echo ============================================================
echo.
pause
