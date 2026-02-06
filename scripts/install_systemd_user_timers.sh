#!/bin/bash
# Install Systemd User Timer for OpenAlgo Health Check

set -e

# Resolve Repo Root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTHCHECK_SCRIPT="$REPO_ROOT/scripts/healthcheck.py"
PYTHON_EXEC="$(which python3)"

# Ensure healthcheck script is executable
chmod +x "$HEALTHCHECK_SCRIPT"

# Systemd User Config Directory
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

SERVICE_FILE="$SYSTEMD_USER_DIR/openalgo-health.service"
TIMER_FILE="$SYSTEMD_USER_DIR/openalgo-health.timer"

echo "Installing Systemd User Service..."

# Create Service File
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=OpenAlgo Health Check
After=network.target

[Service]
Type=oneshot
ExecStart=$PYTHON_EXEC $HEALTHCHECK_SCRIPT
WorkingDirectory=$REPO_ROOT
StandardOutput=append:$REPO_ROOT/logs/healthcheck_service.log
StandardError=append:$REPO_ROOT/logs/healthcheck_service.log

[Install]
WantedBy=default.target
EOF

echo "Created $SERVICE_FILE"

# Create Timer File
cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=openalgo-health.service

[Install]
WantedBy=timers.target
EOF

echo "Created $TIMER_FILE"

# Reload and Enable
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Enabling and starting timer..."
systemctl --user enable openalgo-health.timer
systemctl --user start openalgo-health.timer
systemctl --user list-timers --all | grep openalgo

echo "✅ OpenAlgo Health Check Timer Installed."
