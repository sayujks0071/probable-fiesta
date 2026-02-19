#!/usr/bin/env python3
import os
import sys
import logging
import logging.handlers
import urllib.request
import urllib.error
import urllib.parse
import socket
import json
import time
from datetime import datetime, timedelta

# Configuration
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'healthcheck.log')
LOKI_URL = "http://localhost:3100"
GRAFANA_URL = "http://localhost:3000"
OPENALGO_URL = "http://localhost:5000"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Setup Logging
def setup_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logger = logging.getLogger("HealthCheck")
    logger.setLevel(logging.INFO)

    # File Handler
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10*1024*1024, backupCount=5
    )
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_logging()

def check_port(host, port, timeout=2):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.error(f"Port check failed for {host}:{port}: {e}")
        return False

def check_http(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, socket.timeout, ConnectionRefusedError, Exception) as e:
        # Suppress verbose errors for expected failures when service is down
        # logger.warning(f"HTTP check failed for {url}: {e}")
        return False

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set. Skipping alert.")
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
                logger.info("Telegram alert sent.")
            else:
                logger.error(f"Failed to send Telegram alert: Status {response.status}")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

def query_loki(query, start_time_ns, end_time_ns):
    try:
        params = {
            'query': query,
            'start': start_time_ns,
            'end': end_time_ns,
            'limit': 100
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{LOKI_URL}/loki/api/v1/query_range?{query_string}"

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                results = data.get('data', {}).get('result', [])
                return results
            else:
                logger.warning(f"Loki query failed: {response.status} {response.reason}")
                return []
    except (urllib.error.URLError, socket.timeout, ConnectionRefusedError):
        # Loki is likely down, handled by service check
        return []
    except Exception as e:
        logger.error(f"Loki query error: {e}")
        return []

def run_health_check():
    logger.info("Starting health check...")

    # 1. Service Health
    services = {
        "OpenAlgo": {"port": 5000, "url": f"{OPENALGO_URL}/api/health", "critical": True},
        "Loki": {"port": 3100, "url": f"{LOKI_URL}/ready", "critical": True},
        "Grafana": {"port": 3000, "url": f"{GRAFANA_URL}/api/health", "critical": False},
    }

    service_status = {}
    for name, config in services.items():
        port_ok = check_port("localhost", config["port"])

        http_ok = True
        if port_ok and name != "OpenAlgo":
             http_ok = check_http(config["url"])

        # OpenAlgo might be behind auth or not have /api/health accessible without token
        # So for OpenAlgo, if port is open, we assume it's up for basic check
        if name == "OpenAlgo":
            status = port_ok
        else:
            status = port_ok and http_ok

        service_status[name] = status

        if not status:
            msg = f"{name} is DOWN (Port: {port_ok})"
            if name != "OpenAlgo":
                msg += f" (HTTP: {http_ok})"

            logger.error(msg)
            if config["critical"]:
                send_telegram_alert(msg)
        else:
            logger.info(f"{name} is UP")

    # 2. Alert Rules (Query Loki)
    # Only if Loki is UP
    if service_status["Loki"]:
        now = time.time()
        start_time = int((now - 300) * 1e9) # 5 minutes ago in nanoseconds
        end_time = int(now * 1e9)

        # Rule 1: High Error Rate
        # Count lines with "ERROR"
        error_query = '{job="openalgo"} |= "ERROR"'
        results = query_loki(error_query, start_time, end_time)
        error_count = sum(len(stream['values']) for stream in results)

        logger.info(f"Error count in last 5m: {error_count}")

        if error_count > 10:
            msg = f"High Error Rate: {error_count} errors in last 5 minutes."
            logger.error(msg)
            send_telegram_alert(msg)

        # Rule 2: Critical Keywords (Auth Failed, Order Rejected)
        critical_keywords = [
            ("Auth failed", "Authentication Failure"),
            ("Order rejected", "Order Rejected"),
            ("broker error", "Broker Error"),
            ("token invalid", "Token Invalid")
        ]

        for keyword, label in critical_keywords:
            query = f'{{job="openalgo"}} |= "{keyword}"'
            results = query_loki(query, start_time, end_time)
            count = sum(len(stream['values']) for stream in results)

            if count > 0:
                msg = f"Critical Alert: {label} detected {count} times in last 5 minutes."
                logger.error(msg)
                send_telegram_alert(msg)

    logger.info("Health check completed.")

if __name__ == "__main__":
    run_health_check()
