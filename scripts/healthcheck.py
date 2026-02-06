#!/usr/bin/env python3
"""
OpenAlgo Health Check & Alert Script
------------------------------------
Runs periodically to:
1. Check if OpenAlgo, Loki, Grafana are running.
2. Query Loki for error spikes and critical failures.
3. Send alerts to Console and Telegram (if configured).
4. Log results to logs/healthcheck.log.
"""

import os
import sys
import logging
import datetime
import json
import urllib.request
import urllib.error
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- Configuration ---
LOKI_URL = "http://localhost:3100"
GRAFANA_URL = "http://localhost:3000"
OA_HOST = os.getenv("FLASK_HOST_IP", "127.0.0.1")
OA_PORT = os.getenv("FLASK_PORT", "5000")
OPENALGO_URL = f"http://{OA_HOST}:{OA_PORT}"

# Alert Thresholds
ERROR_SPIKE_THRESHOLD = 0  # Alert if > 0 errors in 5m

# Telegram Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Setup Logging
# Resolve repo root relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LOG_DIR = REPO_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "healthcheck.log"

logger = logging.getLogger("healthcheck")
logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# File Handler
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)


def send_telegram_alert(message):
    """Send alert to Telegram if configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 OpenAlgo Alert 🚨\n\n{message}",
        "parse_mode": "Markdown"
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            pass
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")


def check_service(name, url, expected_status=200):
    """Check if a service is reachable."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == expected_status:
                return True, "OK"
            return False, f"Status {response.status}"
    except urllib.error.URLError as e:
        return False, f"Unreachable: {e}"
    except Exception as e:
        return False, str(e)


def query_loki(query, start_time_ns):
    """Query Loki for logs."""
    try:
        base_url = f"{LOKI_URL}/loki/api/v1/query_range"
        params = {
            "query": query,
            "start": start_time_ns,
            "limit": 100
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("data", {}).get("result", [])
    except Exception as e:
        logger.error(f"Loki query failed: {e}")
        return []


def check_alerts():
    """Run alert checks via Loki."""
    alerts = []

    # 5 minutes ago in nanoseconds
    now = datetime.datetime.now(datetime.timezone.utc)
    start_time = now - datetime.timedelta(minutes=5)
    start_ns = int(start_time.timestamp() * 1e9)

    # 1. Error Spike
    # Query: Logs with level=ERROR or containing "ERROR"
    error_query = '{job="openalgo"} |= "ERROR"'
    results = query_loki(error_query, start_ns)

    error_count = 0
    for stream in results:
        # Loki returns values as [timestamp, line]
        error_count += len(stream.get("values", []))

    if error_count > ERROR_SPIKE_THRESHOLD:
        alerts.append(f"High ERROR rate: {error_count} errors in last 5m.")

    # 2. Critical Patterns
    patterns = [
        ("Auth failed", '{job="openalgo"} |= "Auth failed"'),
        ("Token Invalid", '{job="openalgo"} |= "token invalid"'),
        ("Symbol Not Found", '{job="openalgo"} |= "symbol not found"'),
        ("Order Rejected", '{job="openalgo"} |= "order rejected"'),
        ("Broker Error", '{job="openalgo"} |= "broker error"')
    ]

    for label, query in patterns:
        res = query_loki(query, start_ns)
        count = 0
        for stream in res:
            count += len(stream.get("values", []))

        if count > 0:
            alerts.append(f"Critical Event: {label} detected ({count} times).")

    return alerts


def main():
    logger.info("Starting Health Check...")

    health_status = {}

    # 1. Service Health
    # Check Loki
    loki_ok, loki_msg = check_service("Loki", f"{LOKI_URL}/ready")
    health_status["Loki"] = loki_ok
    if not loki_ok:
        logger.error(f"Loki Down: {loki_msg}")

    # Check Grafana
    graf_ok, graf_msg = check_service("Grafana", f"{GRAFANA_URL}/api/health")
    health_status["Grafana"] = graf_ok
    if not graf_ok:
        logger.error(f"Grafana Down: {graf_msg}")

    # Check OpenAlgo
    # OpenAlgo might require auth for some endpoints, but root or login usually responds
    oa_ok, oa_msg = check_service("OpenAlgo", OPENALGO_URL)
    health_status["OpenAlgo"] = oa_ok
    if not oa_ok:
        logger.warning(f"OpenAlgo Unreachable: {oa_msg}") # Warning, as it might just be stopped

    # 2. Run Alerts (Only if Loki is UP)
    if loki_ok:
        active_alerts = check_alerts()
        if active_alerts:
            alert_msg = "\n".join(active_alerts)
            logger.error(f"ALERTS TRIGGERED:\n{alert_msg}")
            send_telegram_alert(alert_msg)
        else:
            logger.info("No active alerts.")
    else:
        logger.warning("Skipping log alerts because Loki is down.")

    # Summary
    logger.info(f"Health Check Complete. Status: {json.dumps(health_status)}")

if __name__ == "__main__":
    main()
