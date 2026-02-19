#!/bin/bash

# Get the absolute path to the repo root
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
LOG_PATH="$REPO_ROOT/logs/healthcheck_cron.log"
PYTHON_EXEC=$(which python3)

# Check if healthcheck script is executable
chmod +x "$SCRIPT_PATH"

echo "Installing OpenAlgo Health Check cron job..."
echo "Repo Root: $REPO_ROOT"

# Construct the cron command
# We embed environment variables if they are currently set
ENV_PREFIX=""
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    ENV_PREFIX="TELEGRAM_BOT_TOKEN=\"$TELEGRAM_BOT_TOKEN\" TELEGRAM_CHAT_ID=\"$TELEGRAM_CHAT_ID\" "
    echo "   Including Telegram credentials in cron job."
fi

if [ -n "$OPENALGO_LOG_JSON" ]; then
    ENV_PREFIX="${ENV_PREFIX}OPENALGO_LOG_JSON=\"$OPENALGO_LOG_JSON\" "
fi

# The command: cd to root, set env, run script, redirect output
CRON_CMD="*/5 * * * * cd $REPO_ROOT && $ENV_PREFIX$PYTHON_EXEC $SCRIPT_PATH >> $LOG_PATH 2>&1"

# Check if a similar cron job already exists (grep for the script path)
if crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH" >/dev/null; then
    echo "⚠️  Cron job for healthcheck already exists. Skipping installation."
    echo "   To force update, remove it with crontab -e and re-run this script."
else
    # Append the new job
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✅ Cron job installed successfully."
    echo "   Schedule: Every 5 minutes"
    echo "   Logs: $LOG_PATH"
fi
