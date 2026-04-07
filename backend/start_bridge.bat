@echo off
echo Starting Midas MT5 Bridge...
cd /d "%~dp0"
python mt5_bridge.py %*
