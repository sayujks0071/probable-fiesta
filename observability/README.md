# OpenAlgo Observability Stack

This directory contains the configuration for a local "drain" observability stack using Grafana, Loki, and Promtail.

## Components
- **Loki**: Log aggregation system (port 3100).
- **Promtail**: Log shipper that tails local log files (`../logs/*.log`) and sends them to Loki.
- **Grafana**: Visualization dashboard (port 3000).

## Setup
### Prerequisites
- Docker and Docker Compose installed.
- Python 3 installed.

### Quick Start
1.  **Start the Stack**:
    ```bash
    make obs-up
    ```
    This starts Loki, Promtail, and Grafana in the background.

2.  **Verify Status**:
    ```bash
    make status
    ```

3.  **Run OpenAlgo**:
    ```bash
    make run
    ```
    Logs will be written to `logs/openalgo.log` and automatically shipped to Loki.

4.  **View Logs**:
    - Open Grafana at [http://localhost:3000](http://localhost:3000).
    - Login with `admin` / `admin`.
    - Go to **Dashboards** -> **OpenAlgo Dashboard**.
    - You can also explore logs via **Explore** -> Select **Loki** datasource -> Query `{job="openalgo"}`.

## Monitoring & Alerts
A local healthcheck script runs periodically to monitor the system.

### Install Schedulers
To install the background health check (systemd timer or cron):
```bash
make install-obs
```
This sets up a check every 5 minutes.

### Alerts
- **Desktop Notifications**: If on Linux/Mac, you'll get a desktop notification for critical errors.
- **Telegram**: Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables to receive alerts via Telegram.

### Health Logs
Health check logs are written to `logs/healthcheck.log`.

## Redaction
All sensitive data (API keys, tokens, passwords) is automatically redacted from logs before being written to disk or shipped to Loki.

## Troubleshooting
- **Logs not showing up?**
    - Check if Promtail is running: `docker ps`
    - Check Promtail logs: `cd observability && docker compose logs promtail`
    - Ensure `logs/openalgo.log` exists and is being written to.
- **Grafana shows "Data Source not found"?**
    - Restart the stack: `make obs-down && make obs-up`.
