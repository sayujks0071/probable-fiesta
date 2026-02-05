#!/bin/bash
set -e

# Resolve repo root relative to this script
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
LOG_FILE="$REPO_ROOT/logs/cron_health.log"
CRON_CMD="*/5 * * * * cd $REPO_ROOT && /usr/bin/python3 scripts/healthcheck.py >> $LOG_FILE 2>&1"

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: healthcheck.py not found at $SCRIPT_PATH"
    exit 1
fi

# Check if job already exists
(crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH") && echo "Cron job already exists." && exit 0

echo "Adding cron job..."
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "✅ Cron job installed."
crontab -l | grep healthcheck.py
