@echo off
echo Starting Midas Backend...
cd /d "%~dp0"
uvicorn main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
