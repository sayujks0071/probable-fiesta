#!/usr/bin/env python3
import requests
import os
import sys
import logging
import time
import json
from pathlib import Path
from datetime import datetime

# Setup logging
def setup_logging():
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "alerts.log"

    # Use standard format so Promtail can parse it
    # We use 'alert_monitor' as logger name in the logs
    fmt = '[%(asctime)s] %(levelname)s %(name)s: %(message)s'

    # Configure root logger to write to file
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format=fmt
    )

    # Also print to stdout
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(console)

setup_logging()
# Important: Use 'alert_monitor' as the logger name
logger = logging.getLogger("alert_monitor")

def query_loki(query, start_ts, end_ts):
    """Query Loki for logs matching the query within the time range."""
    url = "http://localhost:3100/loki/api/v1/query_range"
    params = {
        "query": query,
        "start": int(start_ts * 1e9), # Nanoseconds
        "end": int(end_ts * 1e9),
        "limit": 1000
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'success':
            return data['data']['result']
        else:
            logger.error(f"Loki query failed: {data}")
            return []
    except requests.exceptions.ConnectionError:
        logger.warning("Could not connect to Loki. Is it running?")
        return []
    except Exception as e:
        logger.error(f"Error querying Loki: {e}")
        return []

def send_telegram(message):
    """Send alert via Telegram if configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.debug("Telegram not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing). Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Telegram notification sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def check_alerts():
    # Look back 5 minutes
    now = time.time()
    five_min_ago = now - 300

    alerts_triggered = False

    # 1. Check for ERROR logs
    # We filter out our own logs (logger="alert_monitor") to prevent feedback loops
    # Promtail pipeline extracts 'logger' label using regex or JSON
    error_query = '{job="openalgo", logger!="alert_monitor"} |= "ERROR"'
    results = query_loki(error_query, five_min_ago, now)

    error_count = 0
    if results:
        for stream in results:
            error_count += len(stream.get('values', []))

    # Threshold for errors (configurable via env, default 5)
    error_threshold = int(os.getenv("ALERT_ERROR_THRESHOLD", 5))

    if error_count >= error_threshold:
        msg = f"🚨 ALERT: High Error Rate! Found {error_count} errors in last 5m (Threshold: {error_threshold})."
        logger.warning(msg)
        send_telegram(msg)
        alerts_triggered = True
    elif error_count > 0:
        logger.info(f"Found {error_count} errors (below threshold {error_threshold}).")

    # 2. Critical Patterns (Immediate Alert)
    # Patterns: "Auth failed", "Order rejected", "Broker error"
    critical_patterns = [
        ("Auth failed", "Authentication Failure"),
        ("Order rejected", "Order Rejected"),
        ("Broker error", "Broker Error"),
        ("Token invalid", "Invalid Token")
    ]

    for pattern, label in critical_patterns:
        # Also exclude alert monitor logs just in case we log these strings
        query = f'{{job="openalgo", logger!="alert_monitor"}} |= "{pattern}"'
        results = query_loki(query, five_min_ago, now)

        count = 0
        if results:
            for stream in results:
                count += len(stream.get('values', []))

        if count > 0:
            msg = f"🚨 ALERT: {label} detected! ({count} occurrences in last 5m)"
            logger.warning(msg)
            send_telegram(msg)
            alerts_triggered = True

    if not alerts_triggered:
        logger.info("No alerts triggered.")

if __name__ == "__main__":
    logger.info("Starting alert check...")
    check_alerts()
