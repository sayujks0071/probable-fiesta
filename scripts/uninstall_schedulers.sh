#!/bin/bash
set -e

# Remove systemd timer
if command -v systemctl &> /dev/null; then
    systemctl --user stop openalgo-health.timer 2>/dev/null || true
    systemctl --user disable openalgo-health.timer 2>/dev/null || true
    rm -f ~/.config/systemd/user/openalgo-health.timer
    rm -f ~/.config/systemd/user/openalgo-health.service
    systemctl --user daemon-reload 2>/dev/null || true
    echo "Systemd user timer removed."
else
    echo "systemctl not found, skipping systemd removal."
fi

# Remove cron job
if command -v crontab &> /dev/null; then
    crontab -l 2>/dev/null | grep -v "scripts/healthcheck.py" | crontab -
    echo "Cron job removed."
else
    echo "crontab not found, skipping cron removal."
fi
