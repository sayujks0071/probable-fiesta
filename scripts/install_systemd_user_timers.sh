#!/bin/bash
set -e

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT_PATH="$REPO_ROOT/scripts/healthcheck.py"
PYTHON_EXEC=$(which python3)

if [ -z "$PYTHON_EXEC" ]; then
    echo "python3 not found"
    exit 1
fi

mkdir -p ~/.config/systemd/user

echo "Installing systemd user service..."

# Create Service
cat <<EOF > ~/.config/systemd/user/openalgo-health.service
[Unit]
Description=OpenAlgo Health Check

[Service]
Type=oneshot
ExecStart=$PYTHON_EXEC $SCRIPT_PATH
WorkingDirectory=$REPO_ROOT
EOF

# Create Timer
cat <<EOF > ~/.config/systemd/user/openalgo-health.timer
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

# Check if systemd is available (might not be in some containers or non-systemd distros)
if command -v systemctl &> /dev/null; then
    systemctl --user daemon-reload
    systemctl --user enable --now openalgo-health.timer
    echo "Systemd user timer installed and started."
    systemctl --user list-timers openalgo-health.timer
else
    echo "systemctl not found. Please use install_cron.sh instead."
fi
