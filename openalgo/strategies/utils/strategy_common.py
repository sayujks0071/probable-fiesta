import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Try to import from openalgo_observability if available
try:
    from openalgo_observability.logging_setup import setup_logging as setup_obs_logging
except ImportError:
    setup_obs_logging = None

def setup_strategy_logging(strategy_name):
    """
    Sets up logging for a strategy.
    Logs to stdout and openalgo/log/strategies/{strategy_name}.log
    """
    # 1. Determine Log Directory
    # Assume this file is in openalgo/strategies/utils/
    # We want openalgo/log/strategies/
    base_dir = Path(__file__).resolve().parent.parent.parent # openalgo/
    log_dir = base_dir / "log" / "strategies"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{strategy_name}.log"

    # 2. Configure Logger
    logger = logging.getLogger(strategy_name)
    logger.setLevel(logging.INFO)

    # Check if handlers already exist to avoid duplicates
    if logger.handlers:
        return logger

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File Handler
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Stream Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.info(f"Logging initialized for {strategy_name}. Log file: {log_file}")

    return logger

def get_strategy_config():
    """
    Retrieves strategy configuration from environment variables.
    Returns a dict with api_key, host, port.
    """
    api_key = os.getenv("OPENALGO_APIKEY")
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1")
    port = int(os.getenv("OPENALGO_PORT", "5001"))

    # If host doesn't include port and port is distinct, append it?
    # Usually OPENALGO_HOST includes protocol and IP/domain.
    # If OPENALGO_HOST is just IP, we might need to add protocol.
    if not host.startswith("http"):
        host = f"http://{host}"

    # If host ends with port, we are good. If not, and we have port, maybe we should use it?
    # But usually host is full URL. Let's assume host is base URL.
    # Existing code constructed host as http://127.0.0.1:{port}

    # If OPENALGO_HOST is default, use port to construct
    if host == "http://127.0.0.1":
        host = f"{host}:{port}"

    if not api_key:
        # Fallback for dev/test if needed, but warn
        # print("WARNING: OPENALGO_APIKEY not set.")
        pass

    return {
        "api_key": api_key,
        "host": host,
        "port": port
    }
