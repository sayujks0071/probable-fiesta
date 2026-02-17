#!/usr/bin/env python3
"""
OpenAlgo Health Check & Alerting Script
Checks service health and queries logs for alerts.
"""
import os
import sys
import logging
import logging.handlers
import subprocess
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta

# Configuration
LOKI_URL = "http://localhost:3100"
GRAFANA_URL = "http://localhost:3000"

# Resolve paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(REPO_ROOT, "logs", "healthcheck.log")

# Alert Thresholds
ERROR_THRESHOLD = 5 # Max errors in 5m
ALERT_LOOKBACK_MINUTES = 5

# Setup Logging for Healthcheck itself
logger = logging.getLogger("HealthCheck")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Rotating File Handler
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1*1024*1024, backupCount=3)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Console Handler
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

def check_service(name, url, timeout=2):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code < 400: # 200-399 is OK
                return True, f"OK ({code})"
            return False, f"HTTP {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def check_process(pattern):
    try:
        # Use pgrep -a -f to get full command line
        # We need to filter out this script itself
        cmd = ["pgrep", "-a", "-f", pattern]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()

        processes = []
        for line in output.strip().split('\n'):
            if not line: continue
            pid, *cmd_parts = line.split(' ', 1)
            cmd_str = cmd_parts[0] if cmd_parts else ""

            # Exclude self (healthcheck.py)
            if "healthcheck.py" in cmd_str:
                continue

            # Exclude simple editors or unrelated things if needed
            processes.append(pid)

        if processes:
            return True, f"Running ({len(processes)} processes: {', '.join(processes)})"
        return False, "Not Running"
    except subprocess.CalledProcessError:
        return False, "Not Running"
    except Exception as e:
        return False, f"Error checking process: {e}"

def query_loki(query, start_time_ns):
    try:
        # Loki query_range endpoint
        url = f"{LOKI_URL}/loki/api/v1/query_range"
        params = urllib.parse.urlencode({
            'query': query,
            'start': str(start_time_ns),
            'limit': 1000
        })
        full_url = f"{url}?{params}"

        with urllib.request.urlopen(full_url, timeout=5) as resp:
            if resp.getcode() == 200:
                data = json.loads(resp.read().decode())
                # Extract results
                # data['data']['result'] is a list of streams
                # each stream has 'values' -> [[ts, line], ...]
                count = 0
                lines = []
                for stream in data.get('data', {}).get('result', []):
                    values = stream.get('values', [])
                    count += len(values)
                    for v in values:
                        lines.append(v[1]) # The log line
                return count, lines
            else:
                logger.error(f"Loki Query Failed: {resp.getcode()}")
                return 0, []
    except Exception as e:
        logger.error(f"Loki Connection Failed: {e}")
        return 0, []

def send_alert(title, message):
    alert_msg = f"🚨 {title}\n{message}"
    logger.warning(alert_msg)

    # 1. Telegram
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        try:
            url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            payload = json.dumps({"chat_id": tg_chat, "text": alert_msg}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info("Telegram notification sent.")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    # 2. Desktop Notification (Linux/Mac)
    try:
        if sys.platform == "linux":
            # Check if notify-send exists
            subprocess.run(["which", "notify-send"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["notify-send", title, message], check=False)
        elif sys.platform == "darwin":
             subprocess.run(["osascript", "-e", f'display notification "{message}" with title "{title}"'], check=False)
    except Exception:
        pass # Ignore errors here

def main():
    logger.info("--- Starting Health Check ---")

    # 1. Service Health
    loki_ok, loki_msg = check_service("Loki", f"{LOKI_URL}/ready")
    grafana_ok, graf_msg = check_service("Grafana", f"{GRAFANA_URL}/login")

    # Check OpenAlgo Process (look for python scripts running openalgo or app.py)
    # Just looking for "openalgo" usually finds the directory path in command line
    # A better pattern might be needed, but "openalgo" is broad enough.
    oa_ok, oa_msg = check_process("openalgo")

    logger.info(f"Loki: {loki_msg}")
    logger.info(f"Grafana: {graf_msg}")
    logger.info(f"OpenAlgo: {oa_msg}")

    if not loki_ok:
        send_alert("System Alert", "Loki is DOWN. Observability compromised.")

    # 2. Log Analysis (Alerting)
    if loki_ok:
        # Current time in ns
        now_ns = time.time_ns()
        # Start time: ALERT_LOOKBACK_MINUTES ago
        start_ns = now_ns - (ALERT_LOOKBACK_MINUTES * 60 * 1_000_000_000)

        # A. Error Spike
        # Query: {job="openalgo"} |= "ERROR"
        error_count, error_lines = query_loki('{job="openalgo"} |= "ERROR"', start_ns)
        logger.info(f"Errors in last {ALERT_LOOKBACK_MINUTES}m: {error_count}")

        if error_count > ERROR_THRESHOLD:
            sample = "\n".join(error_lines[:3])
            send_alert("High Error Rate", f"Found {error_count} errors in last {ALERT_LOOKBACK_MINUTES}m.\nSample:\n{sample}")

        # B. Critical Keywords (Immediate)
        # "Auth failed", "Token invalid", "Order rejected", "Broker error"
        critical_patterns = ["Auth failed", "Token invalid", "Order rejected", "Broker error", "Invalid symbol"]
        # Construct query: {job="openalgo"} |~ "(?i)Auth failed|Token invalid|..."
        regex = "|".join(critical_patterns)
        crit_count, crit_lines = query_loki(f'{{job="openalgo"}} |~ "(?i){regex}"', start_ns)

        if crit_count > 0:
            sample = "\n".join(crit_lines[:3])
            send_alert("Critical Event", f"Found {crit_count} critical events.\nSample:\n{sample}")

    logger.info("--- Health Check Complete ---")

if __name__ == "__main__":
    main()
