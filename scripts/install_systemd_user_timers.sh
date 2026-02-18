#!/bin/bash
set -e

# Get absolute path to scripts
REPO_ROOT=$(dirname "$(dirname "$(readlink -f "$0")")")
HEALTH_SCRIPT="$REPO_ROOT/scripts/healthcheck.py"
ALERT_SCRIPT="$REPO_ROOT/scripts/local_alert_monitor.py"

# Ensure scripts are executable
chmod +x "$HEALTH_SCRIPT"
chmod +x "$ALERT_SCRIPT"

# Systemd User Directory
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

echo "Installing Systemd User Timers..."

# --- Health Check Service ---
cat > "$SYSTEMD_DIR/openalgo-health.service" <<EOF
[Unit]
Description=OpenAlgo Health Check

[Service]
Type=oneshot
ExecStart=$HEALTH_SCRIPT
WorkingDirectory=$REPO_ROOT
EOF

# --- Health Check Timer ---
cat > "$SYSTEMD_DIR/openalgo-health.timer" <<EOF
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

# --- Alert Monitor Service ---
cat > "$SYSTEMD_DIR/openalgo-alert.service" <<EOF
[Unit]
Description=OpenAlgo Alert Monitor

[Service]
Type=oneshot
ExecStart=$ALERT_SCRIPT
WorkingDirectory=$REPO_ROOT
EOF

# --- Alert Monitor Timer ---
cat > "$SYSTEMD_DIR/openalgo-alert.timer" <<EOF
[Unit]
Description=Run OpenAlgo Alert Monitor every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

# Reload and Enable
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Enabling and starting timers..."
systemctl --user enable --now openalgo-health.timer
systemctl --user enable --now openalgo-alert.timer

echo "✅ Systemd timers installed and started."
echo "Check status with: systemctl --user list-timers"
