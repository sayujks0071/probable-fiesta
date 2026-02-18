# OpenAlgo Observability Stack

This directory contains the configuration for a local observability stack using **Loki, Promtail, and Grafana**.
This allows you to monitor OpenAlgo logs, visualize errors, and get alerts locally without external cloud services.

## Components

1.  **Loki**: Log aggregation system (like Prometheus, but for logs).
2.  **Promtail**: Agent that ships logs from `./logs/*.log` to Loki.
3.  **Grafana**: Visualization dashboard.
4.  **Healthcheck Scripts**: Python scripts in `../scripts/` to monitor system health.

## Quick Start

### 1. Start the Stack
Run the following command from the repo root:
```bash
make obs-up
```
This starts Loki (port 3100), Grafana (port 3000), and Promtail.

### 2. Access Grafana
- URL: http://localhost:3000
- User: `admin`
- Pass: `admin`

A default **OpenAlgo Dashboard** is pre-provisioned. Go to **Dashboards > OpenAlgo Local Dashboard**.

### 3. Run OpenAlgo with Logging
Run OpenAlgo as usual:
```bash
make run
```
Logs are written to `./logs/openalgo.log` and automatically ingested by Loki.

### 4. View Logs
You can view logs in Grafana **Explore** view:
- Select datasource: **Loki**
- Query: `{job="openalgo"}`

Or use the CLI shortcut:
```bash
make obs-logs
```

## Scheduled Monitoring

To enable automatic health checks and alerts (every 5 minutes):

**Option A: Systemd Timers (Recommended for Linux)**
```bash
make install-obs
```
This installs user-level systemd timers (`openalgo-health.timer`, `openalgo-alert.timer`).

**Option B: Cron Jobs (Fallback)**
```bash
make install-obs-cron
```
This adds entries to your crontab.

**Uninstall Schedulers**
```bash
make uninstall-obs
```

## Alerts

The local alert monitor (`scripts/local_alert_monitor.py`) checks for:
- High error rate (> 5 errors in 5 min)
- Critical keywords: "Auth failed", "Order rejected", "Broker error"

**Telegram Notifications (Optional)**
Set environment variables in your shell or `.env`:
- `TELEGRAM_BOT_TOKEN`: Your bot token
- `TELEGRAM_CHAT_ID`: Your chat ID

If set, alerts will be sent to Telegram. Otherwise, they are logged to `logs/alerts.log`.

## Redaction
Sensitive data (API keys, passwords, tokens) is automatically redacted from logs by `openalgo_observability/logging_setup.py` before being written to disk.
