#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install --quiet pandas yfinance exchange_calendars
python3 ibs_assistant.py
