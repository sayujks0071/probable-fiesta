#!/bin/bash

REPO_ROOT=$(pwd)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/openalgo-healthcheck.service"
TIMER_FILE="$SERVICE_DIR/openalgo-healthcheck.timer"

echo "Removing Systemd Timer..."
if systemctl --user is-active --quiet openalgo-healthcheck.timer; then
    systemctl --user stop openalgo-healthcheck.timer
    systemctl --user disable openalgo-healthcheck.timer
fi
rm -f "$SERVICE_FILE" "$TIMER_FILE"
systemctl --user daemon-reload
echo "✅ Systemd Timer removed."

echo "Removing Cron Job..."
if crontab -l 2>/dev/null | grep -q "$SCRIPT_PATH"; then
    (crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH") | crontab -
    echo "✅ Cron job removed."
else
    echo "No cron job found."
fi

echo "Schedulers uninstalled."
