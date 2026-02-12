#!/usr/bin/env python3
import os
import sys
import time
import socket
import logging
import argparse
import datetime
import re
import json
from pathlib import Path

# Setup logging for this script
# Find repo root
try:
    REPO_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    REPO_ROOT = Path(os.getcwd())

LOG_DIR = REPO_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "healthcheck.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
# Also print to console if interactive
if sys.stdout.isatty():
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)

# Configuration
OPENALGO_HOST = os.getenv("OPENALGO_HOST", "127.0.0.1")
OPENALGO_PORT = int(os.getenv("FLASK_PORT", 5000))
LOKI_URL = "http://127.0.0.1:3100/ready"
GRAFANA_URL = "http://127.0.0.1:3000/login"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ERROR_THRESHOLD = int(os.getenv("ERROR_THRESHOLD", 5)) # Max errors in last 5 mins
LOG_SCAN_MINUTES = 5

def check_port(host, port, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False
    except Exception as e:
        logging.error(f"Port check error: {e}")
        return False

def check_http(url):
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception as e:
        # 404/403 might still mean it's up, but /ready should be 200.
        # For Grafana /login is 200.
        logging.warning(f"HTTP check failed for {url}: {e}")
        return False

def send_notification(subject, message):
    logging.warning(f"ALERT: {subject} - {message}")

    # 1. Desktop Notification
    try:
        if sys.platform == "darwin":
            os.system(f"""osascript -e 'display notification "{message}" with title "{subject}"'""")
        elif sys.platform.startswith("linux"):
            # Try notify-send
            if os.system(f"notify-send '{subject}' '{message}'") != 0:
                pass
    except Exception:
        pass

    # 2. Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            import urllib.request
            import urllib.parse
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": f"{subject}\n{message}"}).encode()
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req) as resp:
                pass
        except Exception as e:
            logging.error(f"Failed to send Telegram alert: {e}")

def scan_logs_for_errors(log_file):
    if not log_file.exists():
        return

    # Read last 1MB
    file_size = log_file.stat().st_size
    read_size = 1024 * 1024

    errors = []
    auth_failures = []

    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            if file_size > read_size:
                f.seek(file_size - read_size)

            lines = f.readlines()

            now = datetime.datetime.now()
            cutoff = now - datetime.timedelta(minutes=LOG_SCAN_MINUTES)

            # Timestamp regexes
            # Standard: [2024-01-29 12:00:00,123]
            # JSON: "timestamp": "2024-01-29T12:00:00.123456"
            std_ts_re = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')

            for line in lines:
                # Check if line is recent
                ts = None
                try:
                    if line.strip().startswith('{'):
                        # JSON
                        data = json.loads(line)
                        ts_str = data.get('timestamp')
                        if ts_str:
                            # Handle ISO format. datetime.fromisoformat handles T separator.
                            # Replace Z with +00:00 for Python < 3.11 compatibility
                            ts = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    else:
                        # Standard
                        match = std_ts_re.search(line)
                        if match:
                            ts = datetime.datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                except Exception:
                    continue

                if ts:
                    # Robust timezone handling: convert everything to naive local time for comparison with now()
                    if ts.tzinfo is not None:
                         # Convert aware datetime to local time and strip tzinfo
                        ts = ts.astimezone().replace(tzinfo=None)

                    if ts >= cutoff:
                        # Check for errors
                        if "ERROR" in line:
                            errors.append(line)
                        if re.search(r'(?i)auth.*fail|token.*invalid|rejected', line):
                            auth_failures.append(line)

    except Exception as e:
        logging.error(f"Error scanning logs: {e}")
        return

    # Analyze
    if len(errors) > ERROR_THRESHOLD:
        send_notification("High Error Rate", f"Found {len(errors)} errors in last {LOG_SCAN_MINUTES} mins.")

    if auth_failures:
        send_notification("Critical Event", f"Found {len(auth_failures)} critical events (Auth/Order).")


def main():
    logging.info("Starting health check...")

    # 1. Check OpenAlgo
    if not check_port(OPENALGO_HOST, OPENALGO_PORT):
        # Only alert if it should be running?
        # Assume if healthcheck is running, OpenAlgo should be running.
        send_notification("Service Down", f"OpenAlgo is not reachable on port {OPENALGO_PORT}")
        logging.error("OpenAlgo DOWN")
    else:
        logging.info("OpenAlgo UP")

    # 2. Check Observability
    if not check_http(LOKI_URL):
        logging.warning("Loki DOWN or not ready")

    if not check_http(GRAFANA_URL):
        logging.warning("Grafana DOWN")

    # 3. Scan Logs
    log_file = LOG_DIR / "openalgo.log"
    scan_logs_for_errors(log_file)

    logging.info("Health check complete.")

if __name__ == "__main__":
    main()
