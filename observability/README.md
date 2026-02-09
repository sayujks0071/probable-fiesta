# OpenAlgo Local Observability Stack

This directory contains the configuration for a local-first observability stack using **Grafana, Loki, and Promtail**. It is designed to run alongside the OpenAlgo Python application, ingesting logs and providing dashboards and alerts without sending data to the cloud.

## Components

- **Loki** (Port 3100): Log aggregation system.
- **Promtail**: Log shipper. Tails `logs/*.log` from the repository root and pushes to Loki.
- **Grafana** (Port 3000): Visualization. Connects to Loki.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.9+ (for OpenAlgo)

### 1. Start Observability Stack
Run from the repo root:
```bash
make obs-up
```
This will start Loki, Promtail, and Grafana in the background.

- **Grafana URL**: [http://localhost:3000](http://localhost:3000)
- **Default Login**: admin / admin

### 2. Run OpenAlgo with Logging
Run the main startup script:
```bash
make run
```
Logs will be written to `logs/openalgo.log` (rotating). Promtail will pick them up immediately.

### 3. View Logs & Dashboards
1. Open Grafana.
2. Go to **Dashboards > OpenAlgo Dashboard**.
3. You should see panels for "Error Rate" and "Order Activity".
4. To explore raw logs, go to **Explore**, select **Loki** datasource, and use query:
   ```
   {job="openalgo"}
   ```

## Scheduled Monitoring (Health Checks & Alerts)

We provide scripts to periodically check if OpenAlgo is running and if any critical errors (like auth failures) are found in the logs.

### Install Monitoring (Systemd Timer - Recommended)
This runs a health check every 5 minutes.
```bash
make install-monitoring
```
Logs are written to `logs/healthcheck.log`.

### Uninstall Monitoring
```bash
make uninstall-monitoring
```

### Alerts
The monitoring script (`scripts/check_alerts.py`) queries Loki for:
- Spikes in `ERROR` logs (>5 in 5m).
- Critical keywords: `auth failed`, `token invalid`, `symbol not found`, `order rejected`.

#### Telegram Notifications
To enable Telegram alerts, create an environment file at `~/.config/openalgo/openalgo.env`:
```bash
mkdir -p ~/.config/openalgo
cat > ~/.config/openalgo/openalgo.env <<EOF
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"
EOF
```
The scheduled monitoring service will automatically load this file.

## Security & Redaction
Logs are automatically redacted for secrets before being written to disk.
- Patterns like `api_key=...`, `Bearer ...`, `password=...` are replaced with `[REDACTED]`.
- This is handled in `openalgo_observability/logging_setup.py`.

## Troubleshooting
- **Logs not showing up?**
  - Check Promtail logs: `make obs-logs`
  - Ensure `logs/openalgo.log` exists and has content.
- **Grafana cannot connect to Loki?**
  - Ensure both are in the same Docker network (default) or `network_mode: host`. (The provided `docker-compose.yml` uses a default bridge network where `loki` hostname resolves).

## JSON Logging
To switch to JSON format logs (better for programmatic parsing), set:
```bash
export OPENALGO_LOG_JSON=1
```
Then restart OpenAlgo.
