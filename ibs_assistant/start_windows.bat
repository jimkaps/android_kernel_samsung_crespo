@echo off
cd /d "%~dp0"
python -m pip install --quiet pandas yfinance exchange_calendars
python ibs_assistant.py
pause
