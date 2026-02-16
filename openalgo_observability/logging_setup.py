# OpenAlgo Observability Setup
import logging
import logging.handlers
import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime

# Sensitive patterns to filter out
# Format: (Regex Pattern, Replacement String)
SENSITIVE_PATTERNS = [
    (r'(api[_-]?key[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(password[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(token[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(secret[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(authorization[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(Bearer\s+)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(enctoken[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
    (r'(access_token[\s]*[=:]\s*)[\w\-\.\+\/=]+', r'\1[REDACTED]'),
]

class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive information from log messages."""

    def filter(self, record):
        try:
            # 1. Filter the main message (record.msg)
            original_msg = str(record.msg)
            filtered_msg = original_msg
            for pattern, replacement in SENSITIVE_PATTERNS:
                filtered_msg = re.sub(pattern, replacement, filtered_msg, flags=re.IGNORECASE)
            record.msg = filtered_msg

            # 2. Filter args if present
            if hasattr(record, 'args') and record.args:
                filtered_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        filtered_arg = arg
                        for pattern, replacement in SENSITIVE_PATTERNS:
                            filtered_arg = re.sub(pattern, replacement, filtered_arg, flags=re.IGNORECASE)
                        filtered_args.append(filtered_arg)
                    else:
                        filtered_args.append(arg)
                record.args = tuple(filtered_args)
        except Exception:
            # If filtering fails, don't crash logging
            pass

        return True

class JsonFormatter(logging.Formatter):
    """Format logs as JSON lines."""
    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(), # Merges msg and args (already filtered)
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)

def setup_logging():
    """Configure structured logging with rotation and redaction."""

    # Prevent double setup
    if os.environ.get('OPENALGO_LOGGING_SETUP_DONE') == 'true':
        return

    log_level_name = os.getenv('OPENALGO_LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    json_mode = os.getenv('OPENALGO_LOG_JSON', '0') == '1'

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates
    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    sensitive_filter = SensitiveDataFilter()

    # Formatter
    if json_mode:
        formatter = JsonFormatter()
    else:
        # Standard format
        fmt = '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
        formatter = logging.Formatter(fmt)

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)

    # 2. File Handler
    # Default to logs/openalgo.log in repo root
    try:
        # Find repo root. This file is in openalgo_observability/logging_setup.py -> ../
        repo_root = Path(__file__).resolve().parent.parent
        log_dir = repo_root / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "openalgo.log"

        # RotatingFileHandler: 10MB max, 5 backups
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=10*1024*1024, # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)

        logging.info(f"Logging initialized. Level: {log_level_name}, JSON: {json_mode}, File: {log_file}")
    except Exception as e:
        # Fallback to console only if file setup fails
        logging.error(f"Failed to set up file logging: {e}")

    # Suppress noisy libs
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    # Mark setup as done
    os.environ['OPENALGO_LOGGING_SETUP_DONE'] = 'true'
