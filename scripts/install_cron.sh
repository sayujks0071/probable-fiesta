#!/bin/bash
set -e

# Setup Cron Job for OpenAlgo Monitoring
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR_SCRIPT="$REPO_ROOT/scripts/monitor.sh"

CRON_JOB="*/5 * * * * $MONITOR_SCRIPT >> $REPO_ROOT/logs/monitor_cron.log 2>&1"

# Check if already exists
(crontab -l 2>/dev/null || true) | grep -q "$MONITOR_SCRIPT"
if [ $? -eq 0 ]; then
    echo "⚠️ Cron job already exists. Skipping."
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Cron job added."
fi

crontab -l | grep "$MONITOR_SCRIPT"
