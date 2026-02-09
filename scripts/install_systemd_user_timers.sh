#!/bin/bash
set -e

# Setup User Systemd Timer for OpenAlgo Monitoring
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR_SCRIPT="$REPO_ROOT/scripts/monitor.sh"
SERVICE_NAME="openalgo-monitor"

# 1. Create Service Unit
cat > "$USER_SYSTEMD_DIR/$SERVICE_NAME.service" <<EOF
[Unit]
Description=OpenAlgo Monitoring Service (Health + Alerts)

[Service]
Type=oneshot
ExecStart=/bin/bash $MONITOR_SCRIPT
WorkingDirectory=$REPO_ROOT
Environment="PATH=$PATH"
# Load environment (e.g. for TELEGRAM tokens)
EnvironmentFile=-%h/.config/openalgo/openalgo.env

[Install]
WantedBy=default.target
EOF

# 2. Create Timer Unit (Every 5 minutes)
cat > "$USER_SYSTEMD_DIR/$SERVICE_NAME.timer" <<EOF
[Unit]
Description=Run OpenAlgo Monitoring every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF

# 3. Reload and Enable
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME.timer"

echo "✅ Systemd Timer installed and started."
systemctl --user list-timers --all | grep "$SERVICE_NAME"
