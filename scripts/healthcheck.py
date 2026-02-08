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
import re
from datetime import datetime, timedelta

# Configuration
LOKI_URL = "http://localhost:3100"
GRAFANA_URL = "http://localhost:3000"
LOG_DIR = os.path.join(os.path.dirname(__file__), "../logs")
LOG_FILE = os.path.join(LOG_DIR, "healthcheck.log")
OPENALGO_LOG_FILE = os.path.join(LOG_DIR, "openalgo.log")

# Alert Thresholds
ERROR_THRESHOLD = 5 # Max errors in 5m
ALERT_LOOKBACK_MINUTES = 5

# Setup Logging for Healthcheck itself
logger = logging.getLogger("HealthCheck")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Rotating File Handler
os.makedirs(LOG_DIR, exist_ok=True)
handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1*1024*1024, backupCount=3)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Console Handler
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

def check_service(name, url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
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
        # Use pgrep
        cmd = ["pgrep", "-f", pattern]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        pids = output.decode().strip().split('\n')
        # Filter out self (healthcheck.py)
        filtered_pids = [p for p in pids if str(os.getpid()) != p]
        if filtered_pids:
            return True, f"Running ({len(filtered_pids)} processes: {', '.join(filtered_pids)})"
        return False, "Not Running"
    except subprocess.CalledProcessError:
        return False, "Not Running"

def query_loki(query, start_time_ns):
    try:
        # Loki query_range endpoint
        url = f"{LOKI_URL}/loki/api/v1/query_range"
        params = urllib.parse.urlencode({
            'query': query,
            'start': start_time_ns,
            'limit': 1000
        })
        full_url = f"{url}?{params}"

        with urllib.request.urlopen(full_url, timeout=5) as resp:
            if resp.getcode() == 200:
                data = json.loads(resp.read().decode())
                # Extract results
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

def scan_log_file(filepath, lookback_minutes=5):
    """Fallback: Scan the last part of the log file for errors."""
    if not os.path.exists(filepath):
        return 0, [], 0, []

    errors = []
    criticals = []

    # Critical patterns
    critical_patterns = [
        r"Auth failed", r"Token invalid", r"Order rejected",
        r"Broker error", r"Invalid symbol"
    ]
    crit_regex = re.compile("|".join(critical_patterns), re.IGNORECASE)

    try:
        # Read last 1MB
        filesize = os.path.getsize(filepath)
        read_size = min(filesize, 1024 * 1024)

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            if filesize > read_size:
                f.seek(filesize - read_size)

            lines = f.readlines()

            # Simple time filter (approximate since format might vary, but we can check if line contains recent timestamp or just scan all recent lines)
            # Assuming lines have timestamp at start like [2026-02-08 14:44:03,754]
            # We will just scan all read lines as "recent" enough for fallback,
            # or try to parse. For robustness, scanning last 1MB is reasonable for "recent" issues.

            for line in lines:
                if "ERROR" in line:
                    errors.append(line.strip())
                if crit_regex.search(line):
                    criticals.append(line.strip())

        return len(errors), errors, len(criticals), criticals
    except Exception as e:
        logger.error(f"Failed to scan log file: {e}")
        return 0, [], 0, []

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

    # Check OpenAlgo Process
    # Look for daily_startup.py or python with openalgo argument
    oa_ok, oa_msg = check_process("daily_startup.py")
    if not oa_ok:
         oa_ok, oa_msg = check_process("openalgo") # Fallback pattern

    logger.info(f"Loki: {loki_msg}")
    logger.info(f"Grafana: {graf_msg}")
    logger.info(f"OpenAlgo: {oa_msg}")

    # 2. Alerting Logic
    if loki_ok:
        # Use Loki
        now = time.time_ns()
        start = now - (ALERT_LOOKBACK_MINUTES * 60 * 1_000_000_000)

        # A. Error Spike
        error_count, error_lines = query_loki('{job="openalgo"} |= "ERROR"', start)
        logger.info(f"Errors (Loki) in last {ALERT_LOOKBACK_MINUTES}m: {error_count}")

        if error_count > ERROR_THRESHOLD:
            sample = "\n".join(error_lines[:3])
            send_alert("High Error Rate", f"Found {error_count} errors in last {ALERT_LOOKBACK_MINUTES}m.\nSample:\n{sample}")

        # B. Critical Keywords
        critical_patterns = ["Auth failed", "Token invalid", "Order rejected", "Broker error", "Invalid symbol"]
        regex = "|".join(critical_patterns)
        crit_count, crit_lines = query_loki(f'{{job="openalgo"}} |~ "(?i){regex}"', start)

        if crit_count > 0:
            sample = "\n".join(crit_lines[:3])
            send_alert("Critical Event", f"Found {crit_count} critical events.\nSample:\n{sample}")

    else:
        # Fallback: Read Log File
        logger.warning("Loki is DOWN. Switching to Log File Fallback.")
        send_alert("System Alert", "Loki is DOWN. Observability compromised. Using fallback log scan.")

        err_count, err_lines, crit_count, crit_lines = scan_log_file(OPENALGO_LOG_FILE)

        logger.info(f"Errors (File Fallback) in last scan: {err_count}")

        if err_count > ERROR_THRESHOLD:
             # Since we scan 1MB, it might be more than 5 mins, but it's a fallback.
             sample = "\n".join(err_lines[-3:])
             send_alert("High Error Rate (Fallback)", f"Found {err_count} errors in recent logs.\nSample:\n{sample}")

        if crit_count > 0:
             sample = "\n".join(crit_lines[-3:])
             send_alert("Critical Event (Fallback)", f"Found {crit_count} critical events in recent logs.\nSample:\n{sample}")

    logger.info("--- Health Check Complete ---")

if __name__ == "__main__":
    main()
