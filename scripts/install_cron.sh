#!/bin/bash
set -e

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
PYTHON_EXEC=$(which python3)

if [ -z "$PYTHON_EXEC" ]; then
    echo "python3 not found"
    exit 1
fi

LOG_FILE="$REPO_ROOT/logs/cron_healthcheck.log"

CRON_CMD="*/5 * * * * $PYTHON_EXEC $SCRIPT_PATH >> $LOG_FILE 2>&1"

# Check if cron is available
if ! command -v crontab &> /dev/null; then
    echo "crontab command not found."
    exit 1
fi

# Check if job already exists (idempotent)
if crontab -l 2>/dev/null | grep -Fq "$SCRIPT_PATH"; then
    echo "Cron job for healthcheck already exists."
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "Cron job installed."
fi

crontab -l | grep "$SCRIPT_PATH"
