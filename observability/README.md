# OpenAlgo Local Observability Stack

This folder contains the setup for local monitoring of OpenAlgo using Grafana, Loki, and Promtail.

## Components
- **Loki**: Log aggregation system (port 3100).
- **Promtail**: Agent that ships logs from `logs/*.log` to Loki.
- **Grafana**: Visualization dashboard (port 3000).

## Setup
1. **Prerequisites**: Ensure Docker and Docker Compose are installed.
2. **Start Stack**:
   ```bash
   make obs-up
   ```
   This will start the containers in the background.

3. **Access Grafana**:
   - URL: http://localhost:3000
   - User: `admin`
   - Pass: `admin`
   - The "OpenAlgo" dashboard should be pre-loaded.

## Scheduled Health Checks
To ensure OpenAlgo stays healthy, you can install a background scheduler that checks for errors and sends alerts.

### Option A: Systemd Timer (Recommended for Linux)
```bash
make install-obs
```
This installs a user-level systemd timer that runs every 5 minutes.

### Option B: Cron Job (Fallback)
```bash
make install-cron
```
This adds a cron job running every 5 minutes.

### Uninstallation
```bash
make uninstall-obs
```

## Logs & Redaction
- Application logs are written to `logs/openalgo.log`.
- Secrets (API keys, tokens) are automatically redacted by the Python logging filter *before* being written to disk.
- To view logs in real-time:
  ```bash
  make obs-logs
  ```

## JSON Logging
To switch from standard text logs to JSON logs (better for programmatic analysis):
```bash
export OPENALGO_LOG_JSON=1
python3 daily_startup.py
```
Promtail is configured to handle both formats.

## Alerts
The health check script (`scripts/healthcheck.py`) scans for:
- "ERROR" log lines (Threshold: >5 in 5 mins).
- Critical keywords: "auth failed", "token invalid", "rejected".

Notifications are sent via:
- Desktop Notification (Mac/Linux).
- Telegram (if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars are set).
