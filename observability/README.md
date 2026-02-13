# OpenAlgo Local Observability Stack

This folder contains the configuration for a local monitoring stack using **Grafana, Loki, and Promtail**. It is designed to run alongside your local OpenAlgo Python application.

## 🚀 Quick Start

### Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/) installed.
- Python 3.8+ installed locally.

### 1. Start Observability Services
From the repository root, run:
```bash
make obs-up
```
This starts:
- **Loki** (Log aggregation) at `http://localhost:3100`
- **Promtail** (Log shipper) tailing `../logs/*.log`
- **Grafana** (Visualization) at `http://localhost:3000`

### 2. Verify Access
- Open **Grafana**: [http://localhost:3000](http://localhost:3000)
- **Login**: `admin` / `admin` (skip password change if desired)
- Go to **Dashboards** -> **Manage** -> **OpenAlgo** -> **OpenAlgo Local Dashboard**.

### 3. Run OpenAlgo
Start your daily routine as usual. Logs will automatically be drained to `./logs/openalgo.log` and picked up by Promtail.
```bash
make run
```
Or manually:
```bash
python daily_startup.py
```

### 4. Check Logs
- View real-time logs in Grafana **Explore** tab.
- Query: `{job="openalgo"}`
- Search for errors: `{job="openalgo"} |= "ERROR"`

---

## 🔔 Alerting & Health Checks

We provide a lightweight Python script (`scripts/healthcheck.py`) that monitors:
1.  **Service Health**: Checks if Loki, Grafana, and OpenAlgo are running.
2.  **Log Spikes**: Queries Loki for high error rates (> 5 errors in 5m).
3.  **Critical Events**: Scans for "Auth failed", "Order rejected", etc.

### Manual Check
```bash
make healthcheck
```

### Automated Monitoring
You can schedule the health check to run every 5 minutes.

**Option A: Systemd User Timer (Linux - Preferred)**
```bash
bash scripts/install_systemd_user_timers.sh
```
*Benefits: Reliable, runs in background, logs to journal.*

**Option B: Cron Job (Linux/Mac)**
```bash
bash scripts/install_cron.sh
```

### Notifications
By default, alerts are logged to console/logs. To enable **Telegram** notifications:
1.  Set environment variables in your shell or `.env` file:
    ```bash
    export TELEGRAM_BOT_TOKEN="your_bot_token"
    export TELEGRAM_CHAT_ID="your_chat_id"
    ```
2.  The healthcheck script will automatically pick these up and send alerts.

---

## 🔒 Security & Redaction

The logging setup (`openalgo_observability/logging_setup.py`) includes a **SensitiveDataFilter** that automatically redacts:
- API Keys (`api_key=...`)
- Bearer Tokens (`Authorization: Bearer ...`)
- Passwords & Secrets

**Note:** Logs are stored locally in `./logs/`. Ensure this directory is `.gitignore`d (it is by default).

## 🛠 Troubleshooting

**Logs not showing in Grafana?**
1.  Check Promtail status: `docker compose logs promtail`
2.  Ensure `./logs/openalgo.log` exists and has content.
3.  Verify the time range in Grafana (top right) covers the last 5 minutes.

**Stop everything**
```bash
make obs-down
```
