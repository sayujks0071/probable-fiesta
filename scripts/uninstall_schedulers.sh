#!/bin/bash
# Uninstall OpenAlgo Health Check Schedulers (Systemd & Cron)

set -e

echo "Uninstalling OpenAlgo Health Check Schedulers..."

# 1. Remove Systemd Timer
if systemctl --user list-units --full -all | grep -q "openalgo-health.timer"; then
    echo "Stopping and disabling systemd timer..."
    systemctl --user stop openalgo-health.timer || true
    systemctl --user disable openalgo-health.timer || true

    rm -f "$HOME/.config/systemd/user/openalgo-health.timer"
    rm -f "$HOME/.config/systemd/user/openalgo-health.service"

    systemctl --user daemon-reload
    echo "Removed systemd units."
else
    echo "Systemd timer not found."
fi

# 2. Remove Cron Job
SCRIPT_NAME="healthcheck.py"
current_cron=$(crontab -l 2>/dev/null || true)

if echo "$current_cron" | grep -q "$SCRIPT_NAME"; then
    echo "Removing cron job..."
    # Remove lines containing script name
    echo "$current_cron" | grep -v "$SCRIPT_NAME" | crontab -
    echo "Cron job removed."
else
    echo "Cron job not found."
fi

echo "✅ Uninstallation Complete."
