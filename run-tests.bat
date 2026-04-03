@echo off
echo ============================================================
echo   MIDAS TRADING SYSTEM - COMPREHENSIVE TEST SUITE
echo ============================================================
echo.

REM Check if backend is running
echo [1/5] Checking backend status...
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: Backend not running on port 8000
    echo Please start backend: cd backend ^&^& python main.py
    echo.
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
)

REM Check if frontend is running
echo [2/5] Checking frontend status...
curl -s http://localhost:3000 >nul 2>&1
if %errorlevel% neq 0 (
    echo INFO: Frontend not running - Playwright will start it automatically
)

echo [3/5] Running backend Python tests...
cd backend
python test_system_comprehensive.py
set BACKEND_RESULT=%errorlevel%
cd ..
echo.

echo [4/5] Running Playwright E2E tests...
echo.
echo Choose test suite:
echo   1. All tests (15-20 min)
echo   2. Critical requirements only (5 min)
echo   3. Quick smoke test (2 min)
echo   4. Stress tests only (5 min)
echo   5. Custom test file
echo.
choice /C 12345 /N /M "Select option (1-5): "

if errorlevel 5 goto custom
if errorlevel 4 goto stress
if errorlevel 3 goto smoke
if errorlevel 2 goto critical
if errorlevel 1 goto all

:all
echo Running all tests...
call npx playwright test
goto results

:critical
echo Running critical requirement tests...
call npx playwright test tests/e2e/03-signal-generation.spec.ts tests/e2e/04-chart-markers.spec.ts tests/e2e/05-trading-styles.spec.ts tests/e2e/06-mt5-execution.spec.ts
goto results

:smoke
echo Running smoke tests...
call npx playwright test tests/e2e/02-dashboard.spec.ts tests/e2e/03-signal-generation.spec.ts
goto results

:stress
echo Running stress tests...
call npx playwright test tests/e2e/07-stress-tests.spec.ts
goto results

:custom
set /p TESTFILE="Enter test file name (e.g., 03-signal-generation): "
call npx playwright test tests/e2e/%TESTFILE%.spec.ts
goto results

:results
set E2E_RESULT=%errorlevel%
echo.

echo [5/5] Generating test report...
call npx playwright show-report --host 127.0.0.1 --port 9323 >nul 2>&1 &
echo.

echo ============================================================
echo   TEST RESULTS SUMMARY
echo ============================================================
echo.
echo Backend Tests: 
if %BACKEND_RESULT% equ 0 (
    echo   [PASS] All backend tests passed
) else (
    echo   [FAIL] Some backend tests failed
)
echo.
echo E2E Tests:
if %E2E_RESULT% equ 0 (
    echo   [PASS] All E2E tests passed
) else (
    echo   [FAIL] Some E2E tests failed
)
echo.
echo ============================================================
echo.
echo HTML Report: http://127.0.0.1:9323
echo Test artifacts: ./test-results/
echo Screenshots: ./test-results/[test-name]/
echo Videos: ./test-results/[test-name]/video.webm
echo.
echo Press any key to exit...
pause >nul
