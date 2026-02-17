#!/bin/bash
# Install OpenAlgo Healthcheck as a Cron Job

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTHCHECK_SCRIPT="$SCRIPT_DIR/healthcheck.py"
PYTHON_BIN="$(which python3)"

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: python3 not found."
    exit 1
fi

CRON_CMD="*/5 * * * * $PYTHON_BIN $HEALTHCHECK_SCRIPT >> $REPO_ROOT/logs/healthcheck_cron.log 2>&1"

# Check if cron job already exists
crontab -l | grep -q "$HEALTHCHECK_SCRIPT"
if [ $? -eq 0 ]; then
    echo "Cron job already exists."
else
    echo "Adding cron job..."
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "Done."
fi
