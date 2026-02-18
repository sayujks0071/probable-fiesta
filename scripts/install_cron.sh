#!/bin/bash
set -e

# Get absolute path to scripts
# Use Python to get absolute path to handle symlinks correctly
REPO_ROOT=$(python3 -c "import os; print(os.path.dirname(os.path.dirname(os.path.abspath('$0'))))")
HEALTH_SCRIPT="$REPO_ROOT/scripts/healthcheck.py"
ALERT_SCRIPT="$REPO_ROOT/scripts/local_alert_monitor.py"

# Ensure scripts are executable
chmod +x "$HEALTH_SCRIPT"
chmod +x "$ALERT_SCRIPT"

echo "Installing Cron Jobs..."

# Use a temporary file to manipulate crontab
TMP_CRON=$(mktemp)
# Get current crontab, ignore error if empty
crontab -l > "$TMP_CRON" 2>/dev/null || true

# Remove existing entries for these scripts to ensure idempotency
# We match by the script filename to avoid duplicates
sed -i "/scripts\/healthcheck.py/d" "$TMP_CRON"
sed -i "/scripts\/local_alert_monitor.py/d" "$TMP_CRON"

# Add new entries (every 5 minutes)
# We use python3 explicitly
echo "*/5 * * * * python3 $HEALTH_SCRIPT >> $REPO_ROOT/logs/cron_health.log 2>&1" >> "$TMP_CRON"
echo "*/5 * * * * python3 $ALERT_SCRIPT >> $REPO_ROOT/logs/cron_alerts.log 2>&1" >> "$TMP_CRON"

# Install new crontab
crontab "$TMP_CRON"
rm "$TMP_CRON"

echo "✅ Cron jobs installed."
echo "Check status with: crontab -l"
