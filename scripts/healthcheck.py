#!/usr/bin/env python3
import sys
import os
import logging
import logging.handlers
import requests
import socket
import subprocess
import time
from pathlib import Path

# Setup logging for healthcheck
def setup_health_logging():
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "healthcheck.log"

    logger = logging.getLogger("healthcheck")
    logger.setLevel(logging.INFO)

    # Check if handler already exists
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=5*1024*1024, # 5MB
            backupCount=3
        )
        # Standard format
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Also print to console
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

    return logger

logger = setup_health_logging()

def check_port(host, port, service_name):
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False
    except Exception as e:
        logger.error(f"Error checking {service_name} port {port}: {e}")
        return False

def check_http(url, service_name, expected_code=200):
    try:
        response = requests.get(url, timeout=2)
        if response.status_code == expected_code:
            return True
        logger.warning(f"{service_name} returned status {response.status_code} (expected {expected_code})")
        return False
    except requests.RequestException as e:
        logger.error(f"Error checking {service_name} at {url}: {e}")
        return False

def check_process(pattern):
    """Check if a process matching the pattern is running using pgrep."""
    try:
        # pgrep -f <pattern> returns 0 if found, 1 if not
        subprocess.check_output(["pgrep", "-f", pattern])
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        # pgrep might not be installed (e.g. strict container)
        logger.warning("pgrep not found, cannot check process status.")
        return False
    except Exception as e:
        logger.error(f"Error checking process {pattern}: {e}")
        return False

def main():
    logger.info("Starting health check...")

    services_status = {}

    # 1. Check OpenAlgo App (Port 5000) - Web Interface
    if check_port("localhost", 5000, "OpenAlgo Web"):
        services_status["OpenAlgo Web"] = "UP"
    else:
        services_status["OpenAlgo Web"] = "DOWN"

    # 2. Check OpenAlgo Processes (Any python script related to openalgo)
    # We check for 'daily_startup.py', 'app.py', or 'strategies'
    # This is a broader check for background processes
    if check_process("openalgo"):
        services_status["OpenAlgo Process"] = "RUNNING"
    else:
        services_status["OpenAlgo Process"] = "NOT FOUND"

    # 3. Check Loki
    if check_http("http://localhost:3100/ready", "Loki"):
        services_status["Loki"] = "UP"
    else:
        services_status["Loki"] = "DOWN"

    # 4. Check Grafana
    if check_http("http://localhost:3000/api/health", "Grafana"):
        services_status["Grafana"] = "UP"
    else:
        services_status["Grafana"] = "DOWN"

    # Log status
    all_critical_healthy = True
    for service, status in services_status.items():
        if status in ["UP", "RUNNING"]:
            logger.info(f"{service}: {status}")
        else:
            logger.error(f"{service}: {status}")
            # Consider Web or Process down as critical?
            # If Web is down but Process is running, maybe partial health?
            # If Loki/Grafana down, definitely critical for observability.
            if service in ["Loki", "Grafana"]:
                all_critical_healthy = False
            # If BOTH Web and Process are down/not found, then OpenAlgo is down.

    openalgo_up = (services_status["OpenAlgo Web"] == "UP") or (services_status["OpenAlgo Process"] == "RUNNING")

    if not openalgo_up:
        logger.error("OpenAlgo seems to be completely DOWN (neither Web Port 5000 nor Process found).")
        all_critical_healthy = False

    if all_critical_healthy:
        logger.info("Health check passed.")
        sys.exit(0)
    else:
        logger.error("Health check failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
