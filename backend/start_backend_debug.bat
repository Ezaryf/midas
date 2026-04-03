@echo off
echo ========================================
echo   Starting Midas Backend (Debug Mode)
echo ========================================
echo.

cd /d %~dp0

echo Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found!
    pause
    exit /b 1
)

echo.
echo Checking dependencies...
python -c "import fastapi, uvicorn, openai, pandas, MetaTrader5" 2>nul
if errorlevel 1 (
    echo ERROR: Missing dependencies!
    echo Run: pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo Testing imports...
python -c "import app.api.routes" 2>nul
if errorlevel 1 (
    echo ERROR: Failed to import routes!
    python -c "import app.api.routes"
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Starting uvicorn server...
echo ========================================
echo.

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

pause
