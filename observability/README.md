# OpenAlgo Observability Setup (Local)

This directory contains the configuration for a lightweight, local observability stack using **Loki, Promtail, and Grafana**. It captures logs from OpenAlgo (Python), stores them in Loki, and visualizes them in Grafana.

## Prerequisites

- **Docker & Docker Compose**: Required for running the observability stack.
- **Python 3.8+**: Required for OpenAlgo and healthcheck scripts.

## Quick Start

1.  **Start Observability Stack**:
    ```bash
    make obs-up
    ```
    This starts Loki (port 3100), Promtail, and Grafana (port 3000).

2.  **Start OpenAlgo**:
    Run the server (logs will be written to `logs/openalgo.log`):
    ```bash
    make server
    ```
    Or run the daily routine:
    ```bash
    make run
    ```

3.  **View Logs & Dashboards**:
    - Open Grafana: [http://localhost:3000](http://localhost:3000)
    - Login: `admin` / `admin` (default)
    - Go to **Dashboards > OpenAlgo Overview**.
    - Go to **Explore** to query logs directly (Select datasource: Loki).

## Logging Configuration

OpenAlgo uses a structured logging module (`openalgo_observability/logging_setup.py`) that:
- Writes logs to `logs/openalgo.log` (rotating, 10MB max, 5 backups).
- Writes logs to Console (stdout/stderr).
- **Redacts Secrets**: Automatically masks API keys, tokens, and passwords.
- **JSON Mode**: Set `OPENALGO_LOG_JSON=1` environment variable to output JSON logs (for easier parsing by Promtail/Loki).

## Scheduled Monitoring & Alerting

A Python healthcheck script (`scripts/healthcheck.py`) runs periodically to:
1.  Check if OpenAlgo is reachable (Port 5001).
2.  Check if Loki and Grafana are UP.
3.  Query Loki for error spikes (default: >5 errors in 5 mins).
4.  Send Alerts (Console + Telegram).

### Enabling Scheduled Checks

**Option A: Systemd Timer (Recommended for Linux)**
```bash
make install-obs
# Uses scripts/install_systemd_user_timers.sh
```

**Option B: Cron Job (Fallback)**
```bash
./scripts/install_cron.sh
```

### Configuring Alerts (Telegram)

Set the following environment variables (in `.env` or system):

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

To test alerts manually:
```bash
python3 scripts/healthcheck.py
```

## Troubleshooting

- **Logs not showing up?**
  - Check if `logs/openalgo.log` exists and has content.
  - Check Promtail logs: `docker compose -f observability/docker-compose.yml logs promtail`.
  - Ensure Promtail volume mount in `docker-compose.yml` points to the correct absolute path (mapped via `../logs`).

- **Permission Issues?**
  - Ensure `logs/` directory is writable by the user running OpenAlgo.
  - Ensure `scripts/*.sh` are executable (`chmod +x scripts/*.sh`).

## Components

- **Loki**: Log aggregation system.
- **Promtail**: Log shipper. Tails `logs/*.log` and pushes to Loki.
- **Grafana**: Visualization dashboard.
- **Healthcheck Script**: Proactive monitoring and alerting.
