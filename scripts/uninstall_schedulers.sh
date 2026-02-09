#!/bin/bash
set -e

# Remove Systemd Timer
SERVICE_NAME="openalgo-monitor"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
systemctl --user stop "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.timer" 2>/dev/null || true
rm -f "$USER_SYSTEMD_DIR/$SERVICE_NAME.service"
rm -f "$USER_SYSTEMD_DIR/$SERVICE_NAME.timer"
systemctl --user daemon-reload

echo "✅ Systemd Timer removed."

# Remove Cron Job
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR_SCRIPT="$REPO_ROOT/scripts/monitor.sh"

(crontab -l 2>/dev/null | grep -v "$MONITOR_SCRIPT") | crontab -

echo "✅ Cron job removed."
