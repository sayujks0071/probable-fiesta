#!/bin/bash
# Install OpenAlgo Healthcheck as a Systemd User Timer

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTHCHECK_SCRIPT="$SCRIPT_DIR/healthcheck.py"
PYTHON_BIN="$(which python3)"

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: python3 not found."
    exit 1
fi

SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

SERVICE_FILE="$SYSTEMD_DIR/openalgo-healthcheck.service"
TIMER_FILE="$SYSTEMD_DIR/openalgo-healthcheck.timer"

echo "Creating service file at $SERVICE_FILE..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=OpenAlgo Health Check Service

[Service]
Type=oneshot
ExecStart=$PYTHON_BIN $HEALTHCHECK_SCRIPT
WorkingDirectory=$REPO_ROOT
StandardOutput=append:$REPO_ROOT/logs/healthcheck_systemd.log
StandardError=append:$REPO_ROOT/logs/healthcheck_systemd.log
EOF

echo "Creating timer file at $TIMER_FILE..."
cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Enabling and starting timer..."
systemctl --user enable --now openalgo-healthcheck.timer

echo "Checking timer status..."
systemctl --user list-timers --all | grep openalgo
echo "Done."
