#!/bin/bash
# Installs the IBS assistant on a Raspberry Pi as a service that starts on boot.
# Run from the ibs_project folder:  bash ibs_assistant/raspberry_pi/install_pi.sh
set -e
cd "$(dirname "$0")/../.."
PROJ="$(pwd)"; ME="$(whoami)"
sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet pandas yfinance exchange_calendars
sed -e "s#/home/pi/ibs_project#$PROJ#g" -e "s#^User=pi#User=$ME#" ibs_assistant/raspberry_pi/ibs-assistant.service \
  | sudo tee /etc/systemd/system/ibs-assistant.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now ibs-assistant
sleep 5
systemctl --no-pager status ibs-assistant | head -5
echo
echo "Done. Open http://$(hostname -I | awk '{print $1}'):8765 on your laptop or phone (same Wi-Fi)."
