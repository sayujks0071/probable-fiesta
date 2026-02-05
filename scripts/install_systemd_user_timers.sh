#!/bin/bash
set -e

# Resolve repo root relative to this script
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/openalgo-health.service"
TIMER_FILE="$SERVICE_DIR/openalgo-health.timer"

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: healthcheck.py not found at $SCRIPT_PATH"
    exit 1
fi

mkdir -p "$SERVICE_DIR"

echo "Creating Service File at $SERVICE_FILE..."
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=OpenAlgo Health Check
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 $SCRIPT_PATH
WorkingDirectory=$REPO_ROOT
StandardOutput=append:$REPO_ROOT/logs/healthcheck_service.log
StandardError=append:$REPO_ROOT/logs/healthcheck_service.log
EOF

echo "Creating Timer File at $TIMER_FILE..."
cat <<EOF > "$TIMER_FILE"
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=openalgo-health.service

[Install]
WantedBy=timers.target
EOF

echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Enabling and starting timer..."
systemctl --user enable openalgo-health.timer
systemctl --user start openalgo-health.timer

echo "✅ Systemd timer installed and started."
systemctl --user list-timers --all | grep openalgo
