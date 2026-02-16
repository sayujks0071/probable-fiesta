#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Configure Logging for Healthcheck
# We write to a separate rotating log file
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "healthcheck.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("HealthCheck")

# Configuration
OPENALGO_URL = os.getenv("OPENALGO_URL", "http://127.0.0.1:5001")
LOKI_URL = os.getenv("LOKI_URL", "http://127.0.0.1:3100")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://127.0.0.1:3000")
ERROR_THRESHOLD = int(os.getenv("ERROR_THRESHOLD", "5")) # Max errors in 5 mins
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(message):
    """Send alert via Console and optional Telegram."""
    logger.error(f"ALERT: {message}")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 OpenAlgo Alert 🚨\n\n{message}"}
            data_bytes = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    logger.info("Telegram alert sent.")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

def check_url(url, description, expect_status=200):
    """Check if a URL is reachable and returns expected status."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == expect_status:
                logger.info(f"✅ {description} is UP ({url})")
                return True
            else:
                msg = f"{description} returned status {resp.status} (expected {expect_status})"
                logger.error(f"❌ {msg}")
                send_alert(msg)
                return False
    except urllib.error.URLError as e:
        msg = f"{description} is DOWN ({url}): {e}"
        logger.error(f"❌ {msg}")
        send_alert(msg)
        return False
    except Exception as e:
        msg = f"{description} check failed: {e}"
        logger.error(f"❌ {msg}")
        return False

def check_loki_errors():
    """Query Loki for recent errors."""
    query = 'count_over_time({job="openalgo"} |= "ERROR" [5m])'
    # Encode query
    params = urllib.parse.urlencode({'query': query})
    url = f"{LOKI_URL}/loki/api/v1/query?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))

            # Parse result
            # Structure: data['data']['result'][0]['value'][1]
            results = data.get('data', {}).get('result', [])
            error_count = 0
            if results:
                # Value is usually [timestamp, count]
                val = results[0].get('value', [0, 0])
                error_count = int(val[1])

            logger.info(f"Loki Error Count (last 5m): {error_count}")

            if error_count > ERROR_THRESHOLD:
                msg = f"High Error Rate detected! {error_count} errors in last 5 minutes."
                send_alert(msg)
                return False
            return True

    except Exception as e:
        logger.warning(f"Failed to query Loki: {e}")
        return False

def main():
    logger.info("--- Starting Health Check ---")

    # 1. Check OpenAlgo
    # OpenAlgo might not expose a simple health endpoint without auth,
    # but /auth/login or / should be reachable
    openalgo_ok = check_url(f"{OPENALGO_URL}/", "OpenAlgo App")

    # 2. Check Observability Stack
    loki_ok = check_url(f"{LOKI_URL}/ready", "Loki")
    grafana_ok = check_url(f"{GRAFANA_URL}/login", "Grafana")

    # 3. Check for Log Errors (only if Loki is up)
    if loki_ok:
        check_loki_errors()

    logger.info("--- Health Check Complete ---")

if __name__ == "__main__":
    main()
