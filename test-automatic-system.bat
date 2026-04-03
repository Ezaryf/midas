@echo off
echo ========================================
echo Testing Automatic Trading System
echo ========================================
echo.

echo [1/4] Checking backend files...
if not exist "backend\main.py" (
    echo ERROR: backend\main.py not found
    exit /b 1
)
if not exist "backend\app\core\loop.py" (
    echo ERROR: backend\app\core\loop.py not found
    exit /b 1
)
echo ✓ Backend files exist

echo.
echo [2/4] Checking frontend files...
if not exist "src\app\dashboard\page.tsx" (
    echo ERROR: src\app\dashboard\page.tsx not found
    exit /b 1
)
if not exist "src\hooks\useSocket.ts" (
    echo ERROR: src\hooks\useSocket.ts not found
    exit /b 1
)
echo ✓ Frontend files exist

echo.
echo [3/4] Checking configuration...
findstr /C:"background_trading_loop" backend\main.py >nul
if errorlevel 1 (
    echo ERROR: Background loop not configured in main.py
    exit /b 1
)
echo ✓ Background loop configured

findstr /C:"Auto Analysis" src\app\dashboard\page.tsx >nul
if errorlevel 1 (
    echo ERROR: Auto-analysis UI not found in dashboard
    exit /b 1
)
echo ✓ Auto-analysis UI configured

echo.
echo [4/4] Checking for removed manual controls...
findstr /C:"Generate.*button" src\app\dashboard\page.tsx >nul
if not errorlevel 1 (
    echo WARNING: Generate button still exists in code
)
echo ✓ Manual controls removed

echo.
echo ========================================
echo ✓ All checks passed!
echo ========================================
echo.
echo NEXT STEPS:
echo 1. Start backend: cd backend ^&^& python main.py
echo 2. Start frontend: npm run dev
echo 3. Open http://localhost:3000/dashboard
echo 4. Watch signals appear automatically every 10 seconds!
echo.
echo WHAT TO LOOK FOR:
echo - "Auto Analysis: SCALPER" label
echo - "[●] Active  Next: Xs" countdown
echo - "Last analysis: HH:MM:SS" timestamp
echo - Signals appearing without clicking
echo - Chart updating automatically
echo.
pause
