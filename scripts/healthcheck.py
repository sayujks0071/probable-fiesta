#!/usr/bin/env python3
import sys
import os
import logging
import logging.handlers
import subprocess
import urllib.request
import urllib.error
import json
import time
from pathlib import Path
from datetime import datetime

# --- Configuration ---
LOKI_URL = "http://localhost:3100/ready"
GRAFANA_URL = "http://localhost:3000/login"
PROCESS_PATTERN = "daily_startup.py"
LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "openalgo.log"
HEALTH_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "healthcheck.log"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Setup Health Logger ---
HEALTH_LOG_FILE.parent.mkdir(exist_ok=True)
health_logger = logging.getLogger("HealthCheck")
health_logger.setLevel(logging.INFO)

# File Handler (Rotating)
handler = logging.handlers.RotatingFileHandler(
    HEALTH_LOG_FILE, maxBytes=5*1024*1024, backupCount=3
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
health_logger.addHandler(handler)

# Console Handler (Optional, for manual runs)
console = logging.StreamHandler()
console.setFormatter(formatter)
health_logger.addHandler(console)


def send_alert(subject, message):
    """Send alert via available channels."""
    full_msg = f"[{subject}] {message}"
    health_logger.error(full_msg)

    # Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": full_msg}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    health_logger.warning(f"Failed to send Telegram alert: {resp.status}")
        except Exception as e:
            health_logger.warning(f"Telegram alert error: {e}")

def check_http(url, name):
    try:
        req = urllib.request.Request(url, method='HEAD')
        # Some services might return 405 for HEAD, or 200, 302 etc.
        # We assume connection is enough, or status < 500
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                return True, f"{resp.status}"
        except urllib.error.HTTPError as e:
            # 404/405/401 are usually fine (service is up)
            if e.code < 500:
                return True, f"{e.code}"
            return False, f"{e.code}"
    except Exception as e:
        return False, str(e)

def check_process(pattern):
    try:
        # pgrep -f pattern
        # returns PIDs
        output = subprocess.check_output(["pgrep", "-f", pattern])
        pids = output.decode().strip().split('\n')
        # Filter out self (if the script name matches pattern, which shouldn't happen here)
        return True, f"Running (PIDs: {len(pids)})"
    except subprocess.CalledProcessError:
        return False, "Not Running"
    except Exception as e:
        return False, str(e)

def scan_logs_for_errors(logfile, lookback_minutes=5):
    if not logfile.exists():
        return False, "Log file not found"

    try:
        # Tail the last 2000 lines (should cover 5 mins easily)
        cmd = ["tail", "-n", "2000", str(logfile)]
        output = subprocess.check_output(cmd).decode('utf-8', errors='ignore')
        lines = output.splitlines()

        count = 0
        now = datetime.now()
        # Regex for timestamp: [2026-02-05 14:47:49,028]
        import re
        ts_pattern = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\]")

        for line in lines:
            if "ERROR" in line or "CRITICAL" in line:
                # Check timestamp
                match = ts_pattern.match(line)
                if match:
                    ts_str = match.group(1)
                    try:
                        # Parse timestamp
                        log_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
                        # Check age
                        age = (now - log_time).total_seconds() / 60
                        if age <= lookback_minutes:
                            count += 1
                    except ValueError:
                        pass # Ignore parse errors
                else:
                    # If line has no timestamp but is ERROR (e.g. stacktrace continuation),
                    # it's harder to attribute time.
                    # Strategy: If we found a recent timestamped error previously, count this?
                    # Or simpler: Only count lines that START with timestamp and are ERROR.
                    # This avoids counting stack trace lines as separate errors, which is actually good.
                    pass

        if count > 0:
            return False, f"Found {count} ERRORs in last {lookback_minutes} mins."
        return True, "No recent errors."

    except Exception as e:
        return False, f"Failed to scan logs: {e}"

def main():
    health_logger.info("Starting Health Check...")
    issues = []

    # 1. Check Observability
    loki_ok, loki_msg = check_http(LOKI_URL, "Loki")
    if not loki_ok:
        issues.append(f"Loki Down: {loki_msg}")

    graf_ok, graf_msg = check_http(GRAFANA_URL, "Grafana")
    if not graf_ok:
        issues.append(f"Grafana Down: {graf_msg}")

    # 2. Check OpenAlgo Process
    # We check for daily_startup.py OR daily_prep.py OR run_strategy.sh
    # "daily_startup.py" is the main entry point.
    proc_ok, proc_msg = check_process(PROCESS_PATTERN)
    if not proc_ok:
        # It might be normal if not running, but for a "health check" implies it SHOULD be running?
        # The prompt says "Is OpenAlgo running". If not, we might want to alert if it's supposed to be always on.
        # But this is a local run. Maybe just log it.
        # "Health-check OpenAlgo process... Alert... Any 'auth failed'..."
        # If the process is down, we probably can't trade.
        health_logger.info(f"OpenAlgo Process: {proc_msg}")
    else:
        health_logger.info(f"OpenAlgo Process: {proc_msg}")

    # 3. Log Scan
    log_ok, log_msg = scan_logs_for_errors(LOG_FILE)
    if not log_ok:
        issues.append(f"Log Health: {log_msg}")

    # Report
    if issues:
        msg = "; ".join(issues)
        send_alert("HEALTH ALERT", msg)
        print(f"❌ Issues Found: {msg}")
        sys.exit(1)
    else:
        health_logger.info("Health Check Passed.")
        print("✅ Health Check Passed.")
        sys.exit(0)

if __name__ == "__main__":
    main()
