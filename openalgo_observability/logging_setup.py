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
        # We modify the record in place.
        original_msg = str(record.msg)
        filtered_msg = original_msg

        try:
            for pattern, replacement in SENSITIVE_PATTERNS:
                filtered_msg = re.sub(pattern, replacement, filtered_msg, flags=re.IGNORECASE)

            record.msg = filtered_msg

            # Filter args if present and are strings
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
            # In case of any error during filtering, just pass the record but log a warning internally?
            # Or just pass it. Safety first: if we can't redact, maybe we shouldn't log?
            # But logging errors is critical. We'll proceed with best effort.
            pass

        return True

class JsonFormatter(logging.Formatter):
    """Format logs as JSON lines."""
    def format(self, record):
        # Apply redaction first if filter hasn't run yet (though filters run before formatters usually)
        # But here we assume the filter is attached to the handler.

        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(), # This uses record.msg and record.args
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "pid": record.process,
            "thread": record.threadName
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra attributes
        if hasattr(record, 'extra_data'):
             log_data.update(record.extra_data)

        return json.dumps(log_data)

def setup_logging():
    """Configure structured logging with rotation and redaction."""

    # Prevent double setup
    if os.environ.get('OPENALGO_LOGGING_SETUP_DONE') == 'true':
        return

    # Check env var for JSON mode
    json_mode = os.getenv('OPENALGO_LOG_JSON', '0') == '1'

    # Determine Log Level
    log_level_name = os.getenv('OPENALGO_LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    # Create Filter
    sensitive_filter = SensitiveDataFilter()

    # Create Formatter
    if json_mode:
        formatter = JsonFormatter()
    else:
        fmt = '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
        formatter = logging.Formatter(fmt)

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)

    # 2. File Handler
    try:
        # Resolve repo root: this file is in openalgo_observability/logging_setup.py
        # So parent -> openalgo_observability, parent -> repo root
        repo_root = Path(__file__).resolve().parent.parent
        log_dir = repo_root / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "openalgo.log"

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=10*1024*1024, # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)

        # Log startup info (this will go to console too)
        logging.info(f"Logging initialized. Level: {log_level_name}, JSON: {json_mode}, File: {log_file}")

    except Exception as e:
        # Fallback to console only
        sys.stderr.write(f"Error setting up file logging: {e}\n")

    # Suppress noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('watchdog').setLevel(logging.WARNING)

    # Mark setup as done
    os.environ['OPENALGO_LOGGING_SETUP_DONE'] = 'true'

if __name__ == "__main__":
    setup_logging()
    logging.info("This is a test info message with api_key=12345secret")
    logging.error("This is an error message")
    try:
        1/0
    except:
        logging.exception("Exception occurred")
