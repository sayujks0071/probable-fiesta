#!/bin/bash
set -e

echo "Uninstalling schedulers..."

# Disable Systemd Timers
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now openalgo-health.timer 2>/dev/null || true
    systemctl --user disable --now openalgo-alert.timer 2>/dev/null || true

    # Remove unit files
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    rm -f "$SYSTEMD_DIR/openalgo-health.service"
    rm -f "$SYSTEMD_DIR/openalgo-health.timer"
    rm -f "$SYSTEMD_DIR/openalgo-alert.service"
    rm -f "$SYSTEMD_DIR/openalgo-alert.timer"

    systemctl --user daemon-reload 2>/dev/null || true
    echo "Removed systemd timers."
fi

# Remove Cron Jobs
if command -v crontab >/dev/null 2>&1; then
    TMP_CRON=$(mktemp)
    crontab -l > "$TMP_CRON" 2>/dev/null || true

    # Check if lines exist before trying to remove
    if grep -q "scripts/healthcheck.py" "$TMP_CRON" || grep -q "scripts/local_alert_monitor.py" "$TMP_CRON"; then
        sed -i "/scripts\/healthcheck.py/d" "$TMP_CRON"
        sed -i "/scripts\/local_alert_monitor.py/d" "$TMP_CRON"
        crontab "$TMP_CRON"
        echo "Removed cron jobs."
    fi
    rm "$TMP_CRON"
fi

echo "✅ Schedulers uninstalled."
