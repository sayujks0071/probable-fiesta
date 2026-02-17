#!/bin/bash
# Uninstall OpenAlgo Healthcheck Schedulers

# 1. Systemd
echo "Stopping and disabling systemd timer..."
systemctl --user stop openalgo-healthcheck.timer
systemctl --user disable openalgo-healthcheck.timer
rm -f "$HOME/.config/systemd/user/openalgo-healthcheck.timer"
rm -f "$HOME/.config/systemd/user/openalgo-healthcheck.service"
systemctl --user daemon-reload
echo "Systemd timer removed."

# 2. Cron
echo "Removing cron job..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
HEALTHCHECK_SCRIPT="$SCRIPT_DIR/healthcheck.py"
crontab -l | grep -v "$HEALTHCHECK_SCRIPT" | crontab -
echo "Cron job removed."

echo "Done."
