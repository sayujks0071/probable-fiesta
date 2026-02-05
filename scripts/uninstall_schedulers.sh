#!/bin/bash

# Uninstall Systemd
echo "Uninstalling Systemd Timers..."
systemctl --user stop openalgo-health.timer 2>/dev/null || true
systemctl --user disable openalgo-health.timer 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/openalgo-health.service"
rm -f "$HOME/.config/systemd/user/openalgo-health.timer"
systemctl --user daemon-reload
echo "Systemd cleanup done."

# Uninstall Cron
echo "Uninstalling Cron Job..."
REPO_ROOT=$(pwd)
SCRIPT_PATH="scripts/healthcheck.py"
# We match loosely on the script name
crontab -l 2>/dev/null | grep -v "healthcheck.py" | crontab -
echo "Cron cleanup done."
