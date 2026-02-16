#!/bin/bash
set -e

REPO_ROOT=$(pwd)
PYTHON_EXEC=$(which python3)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
LOG_FILE="$REPO_ROOT/logs/healthcheck_cron.log"

echo "Installing Cron Job for OpenAlgo Healthcheck..."

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: $SCRIPT_PATH not found. Run from repo root."
    exit 1
fi

CRON_JOB="*/5 * * * * cd $REPO_ROOT && PYTHONPATH=$REPO_ROOT $PYTHON_EXEC $SCRIPT_PATH >> $LOG_FILE 2>&1"

# Check if already installed
if crontab -l 2>/dev/null | grep -q "$SCRIPT_PATH"; then
    echo "Cron job already exists. Updating..."
    # Remove existing and append new
    (crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH"; echo "$CRON_JOB") | crontab -
else
    # Append new
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
fi

echo "✅ Cron job installed."
crontab -l | grep "$SCRIPT_PATH"
