#!/bin/bash

# Get the absolute path to the repo root
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HEALTHCHECK_SCRIPT="$REPO_ROOT/scripts/healthcheck.py"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

# Ensure healthcheck script is executable
chmod +x "$HEALTHCHECK_SCRIPT"

# Create systemd user directory if it doesn't exist
mkdir -p "$USER_SYSTEMD_DIR"

echo "Installing OpenAlgo Health Check timer..."
echo "Repo Root: $REPO_ROOT"
echo "Script: $HEALTHCHECK_SCRIPT"

# Check for Telegram Env Vars
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  TELEGRAM_BOT_TOKEN is not set. Alerts will only be logged locally."
    echo "   Export TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before running this script to enable Telegram alerts."
fi

# Create Service File
# We use Python explicitly. Assuming python3 is in path or /usr/bin/python3
PYTHON_EXEC=$(which python3)

cat > "$USER_SYSTEMD_DIR/openalgo-healthcheck.service" <<EOF
[Unit]
Description=OpenAlgo Health Check
After=network.target

[Service]
Type=oneshot
ExecStart=$PYTHON_EXEC $HEALTHCHECK_SCRIPT
WorkingDirectory=$REPO_ROOT
Environment="TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"
Environment="TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID"
Environment="OPENALGO_LOG_JSON=$OPENALGO_LOG_JSON"

[Install]
WantedBy=default.target
EOF

# Create Timer File
cat > "$USER_SYSTEMD_DIR/openalgo-healthcheck.timer" <<EOF
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Reload systemd
systemctl --user daemon-reload

# Enable and start the timer
systemctl --user enable openalgo-healthcheck.timer
systemctl --user start openalgo-healthcheck.timer

echo "✅ Systemd user timer installed and started."
echo "   Status: systemctl --user status openalgo-healthcheck.timer"
echo "   Logs:   journalctl --user -u openalgo-healthcheck.service -f"
