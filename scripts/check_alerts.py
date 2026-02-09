#!/usr/bin/env python3
import os
import sys
import logging
import json
import time
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
import urllib.error

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - ALERTS - %(levelname)s - %(message)s')
logger = logging.getLogger("Alerts")

LOKI_URL = "http://localhost:3100/loki/api/v1/query_range"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 *OpenAlgo Alert*\n\n{message}",
        "parse_mode": "Markdown"
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                logger.info("Telegram notification sent.")
            else:
                 logger.error(f"Telegram returned status {response.status}")
    except Exception as e:
        logger.error(f"Failed to send Telegram: {e}")

def check_loki(query, start_ts):
    params = {
        'query': query,
        'start': start_ts, # Nanoseconds
        'limit': 100
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f"{LOKI_URL}?{query_string}"

    try:
        with urllib.request.urlopen(full_url, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('data', {}).get('result', [])
            else:
                logger.error(f"Loki query failed: Status {response.status}")
                return []
    except urllib.error.URLError as e:
        logger.error(f"Loki connection failed: {e.reason}")
        return []
    except Exception as e:
        logger.error(f"Loki query failed: {e}")
        return []

def main():
    # Look back 5 minutes
    now = datetime.now()
    start_ts = int((now - timedelta(minutes=5)).timestamp() * 1e9) # nanoseconds

    # 1. Check for Critical Keywords
    critical_keywords = ["auth failed", "token invalid", "symbol not found", "order rejected", "broker error"]
    regex_pattern = "|".join(critical_keywords)
    # Loki uses LogQL. |~ matches regex (case insensitive with (?i) if supported, or just verify pattern)
    # Loki regex is RE2. (?i) is supported at start.
    query_critical = f'{{job="openalgo"}} |~ "(?i)({regex_pattern})"'

    results_critical = check_loki(query_critical, start_ts)
    if results_critical:
        count = sum(len(stream['values']) for stream in results_critical)
        if count > 0:
            msg = f"Found {count} critical events (auth/order failures) in last 5m."
            logger.error(msg)
            send_telegram(msg)

    # 2. Check for ERROR spike
    query_error = '{job="openalgo"} |= "ERROR"'
    results_error = check_loki(query_error, start_ts)

    error_count = 0
    if results_error:
        error_count = sum(len(stream['values']) for stream in results_error)

    THRESHOLD = 5
    if error_count > THRESHOLD:
        msg = f"High ERROR rate detected: {error_count} errors in last 5m (Threshold: {THRESHOLD})."
        logger.error(msg)
        send_telegram(msg)
    else:
        logger.info(f"Error count in last 5m: {error_count} (OK)")

if __name__ == "__main__":
    main()
