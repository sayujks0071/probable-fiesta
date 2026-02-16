#!/bin/bash
set -e

REPO_ROOT=$(pwd)
PYTHON_EXEC=$(which python3)
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/openalgo-healthcheck.service"
TIMER_FILE="$SERVICE_DIR/openalgo-healthcheck.timer"

echo "Installing Systemd Timer for OpenAlgo Healthcheck..."

mkdir -p "$SERVICE_DIR"

# Create Service File
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=OpenAlgo Health Check
After=network.target

[Service]
Type=oneshot
WorkingDirectory=$REPO_ROOT
ExecStart=$PYTHON_EXEC $REPO_ROOT/scripts/healthcheck.py
Environment="PYTHONPATH=$REPO_ROOT"
# Inherit current environment variables if needed, or source .env
# EnvironmentFile=$REPO_ROOT/.env

[Install]
WantedBy=default.target
EOF

# Create Timer File (Run every 5 minutes)
cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Reload and Enable
systemctl --user daemon-reload
systemctl --user enable --now openalgo-healthcheck.timer

echo "✅ Systemd Timer installed and started."
systemctl --user status openalgo-healthcheck.timer --no-pager
