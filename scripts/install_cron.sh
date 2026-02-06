#!/bin/bash
# Install Cron Job for OpenAlgo Health Check

set -e

# Resolve Repo Root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTHCHECK_SCRIPT="$REPO_ROOT/scripts/healthcheck.py"
PYTHON_EXEC="$(which python3)"

# Ensure healthcheck script is executable
chmod +x "$HEALTHCHECK_SCRIPT"

# Cron Schedule (every 5 minutes)
CRON_SCHEDULE="*/5 * * * *"
CMD="$PYTHON_EXEC $HEALTHCHECK_SCRIPT >> $REPO_ROOT/logs/cron_healthcheck.log 2>&1"
JOB="$CRON_SCHEDULE $CMD"

# Check if job already exists
current_cron=$(crontab -l 2>/dev/null || true)

if echo "$current_cron" | grep -q "$HEALTHCHECK_SCRIPT"; then
    echo "⚠️ Cron job already exists for $HEALTHCHECK_SCRIPT. Skipping."
else
    echo "Installing Cron Job..."
    (echo "$current_cron"; echo "$JOB") | crontab -
    echo "✅ Cron Job Installed:"
    crontab -l | grep "$HEALTHCHECK_SCRIPT"
fi
