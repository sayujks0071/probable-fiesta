# OpenAlgo Local Observability

This directory contains the configuration for the local observability stack, powered by **Loki**, **Promtail**, and **Grafana**. It provides a lightweight, local-first solution for monitoring OpenAlgo logs, visualizing metrics, and alerting on errors.

## Prerequisites

*   **Docker** & **Docker Compose**: To run the observability stack.
*   **Python 3**: To run OpenAlgo and the health check scripts.
*   **Make**: (Optional) For easy management commands.

## Quick Start

1.  **Start the Observability Stack**:
    ```bash
    make obs-up
    # OR
    docker compose -f observability/docker-compose.yml up -d
    ```
    This spins up Loki (port 3100), Grafana (port 3000), and Promtail.

2.  **Run OpenAlgo**:
    ```bash
    make run
    # OR
    python3 daily_startup.py
    ```
    OpenAlgo will write logs to `logs/openalgo.log`, which Promtail tails and pushes to Loki.

3.  **View Dashboard**:
    *   Open [http://localhost:3000](http://localhost:3000).
    *   Login with `admin` / `admin`.
    *   Go to **Dashboards** > **OpenAlgo** > **OpenAlgo Local Dashboard**.

## Features

### Logging
*   **Structured Logs**: All logs are written to `logs/openalgo.log`.
*   **Rotation**: Logs rotate automatically (10MB size, 5 backups).
*   **JSON Mode**: Set `OPENALGO_LOG_JSON=1` to emit logs in JSON format for easier parsing.
*   **Redaction**: Sensitive patterns (API keys, tokens, passwords) are automatically redacted (replaced with `[REDACTED]`) before being written to disk or console.

### Dashboard
The default dashboard provides:
*   **Errors (Last 5m)**: Count of log lines containing "ERROR".
*   **Orders Placed**: Count of order placement events.
*   **Auth Failures**: Count of authentication/token errors.
*   **Log Stream**: Real-time view of the logs with search capabilities.

### Health Checks & Alerting
A Python-based health check script (`scripts/healthcheck.py`) runs periodically to:
1.  **Check Services**: Verifies OpenAlgo, Loki, and Grafana are running.
2.  **Analyze Logs**: Queries Loki for error spikes or critical failures (e.g., "Broker error").
3.  **Alert**:
    *   **Desktop Notification**: Native system notification.
    *   **Telegram**: If configured.

#### Enabling Scheduled Checks
To run the health check every 5 minutes automatically:

**Option 1: Systemd (Recommended for Linux)**
```bash
make install-obs
# OR
./scripts/install_systemd_user_timers.sh
```

**Option 2: Cron**
```bash
./scripts/install_cron.sh
```

#### Configuring Telegram Alerts
Set the following environment variables (e.g., in your `.env` file or shell):
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

## Management Commands

The `Makefile` at the repo root simplifies operations:

*   `make obs-up`: Start Loki/Grafana/Promtail.
*   `make obs-down`: Stop the stack.
*   `make obs-logs`: Tail Promtail and App logs.
*   `make status`: Check the status of containers and run a one-off health check.
