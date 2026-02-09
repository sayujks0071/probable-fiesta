#!/usr/bin/env python3
import sys
import os
import logging
import logging.handlers
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Setup logging specifically for healthcheck
def setup_health_logging():
    repo_root = Path(__file__).resolve().parent.parent
    log_dir = repo_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "healthcheck.log"

    logger = logging.getLogger("HealthCheck")
    logger.setLevel(logging.INFO)

    # Clear handlers
    if logger.handlers:
        return logger

    # Rotating file handler
    handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=5*1024*1024, # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    return logger

logger = setup_health_logging()

def check_openalgo_process():
    """Check if OpenAlgo related processes are running."""
    try:
        # pgrep -af openalgo
        result = subprocess.run(['pgrep', '-af', 'openalgo'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # Filter out this healthcheck script itself
            processes = [line for line in result.stdout.splitlines() if 'healthcheck.py' not in line]
            if processes:
                logger.info(f"OpenAlgo Process Check: OK. Found {len(processes)} processes.")
                return True
            else:
                 logger.warning("OpenAlgo Process Check: WARN. No OpenAlgo processes found (excluding healthcheck).")
                 return False
        else:
            logger.warning("OpenAlgo Process Check: FAILED. No processes found.")
            return False
    except FileNotFoundError:
        # pgrep might not be installed
        logger.error("OpenAlgo Process Check: ERROR. pgrep command not found.")
        return False
    except Exception as e:
        logger.error(f"OpenAlgo Process Check: ERROR. {e}")
        return False

def check_url(name, url, expected_status=200):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == expected_status:
                logger.info(f"{name} Check: OK ({url})")
                return True
            else:
                logger.error(f"{name} Check: FAILED. Status {response.status} ({url})")
                return False
    except urllib.error.HTTPError as e:
        # Some health endpoints might return non-200 on failure, but reachable
        if e.code == expected_status:
            logger.info(f"{name} Check: OK ({url})")
            return True
        logger.error(f"{name} Check: FAILED. HTTP {e.code} ({url})")
        return False
    except urllib.error.URLError as e:
        logger.error(f"{name} Check: FAILED. Connection failed: {e.reason} ({url})")
        return False
    except Exception as e:
        logger.error(f"{name} Check: ERROR. {e}")
        return False

def check_observability():
    # Loki readiness
    loki_ok = check_url("Loki", "http://localhost:3100/ready")
    # Grafana login page
    grafana_ok = check_url("Grafana", "http://localhost:3000/login")
    return loki_ok and grafana_ok

def main():
    logger.info("=== Starting Health Check ===")

    algo_up = check_openalgo_process()
    obs_up = check_observability()

    status = "HEALTHY" if (algo_up and obs_up) else "UNHEALTHY"
    logger.info(f"=== Health Check Complete: {status} ===")

    if not (algo_up and obs_up):
        sys.exit(1)

if __name__ == "__main__":
    main()
