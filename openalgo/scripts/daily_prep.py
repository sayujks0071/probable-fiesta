#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
import shutil
import glob
import argparse
from datetime import datetime, timedelta
import httpx
import pandas as pd

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.append(repo_root)

# Try to import SymbolResolver
try:
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    # Fallback if running from within scripts dir without root in path
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from symbol_resolver import SymbolResolver

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyPrep")

DATA_DIR = os.path.join(repo_root, 'openalgo/data')
STATE_DIR = os.path.join(repo_root, 'openalgo/strategies/state')
SESSION_DIR = os.path.join(repo_root, 'openalgo/sessions')
CONFIG_FILE = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')

def check_env():
    logger.info("Checking Environment...")

    # 1. API Key
    if not os.getenv('OPENALGO_APIKEY'):
        logger.warning("OPENALGO_APIKEY not set. Using default 'demo_key'.")
        os.environ['OPENALGO_APIKEY'] = 'demo_key'

    # 2. Paths
    if not os.path.exists(os.path.join(repo_root, 'openalgo')):
        logger.error("Repo structure invalid. 'openalgo' dir not found.")
        sys.exit(1)

    logger.info("Environment OK.")

def purge_stale_state():
    logger.info("Purging Stale State...")

    # 1. Clear PositionManager state
    if os.path.exists(STATE_DIR):
        files = glob.glob(os.path.join(STATE_DIR, "*.json"))
        deleted_count = 0
        for f in files:
            try:
                os.remove(f)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete {f}: {e}")
        logger.info(f"Deleted {deleted_count} state files from {STATE_DIR}")
    else:
        logger.info(f"State dir {STATE_DIR} does not exist, skipping.")

    # 2. Clear Cached Instruments
    inst_file = os.path.join(DATA_DIR, 'instruments.csv')
    if os.path.exists(inst_file):
        try:
            os.remove(inst_file)
            logger.info("Deleted cached instruments.csv")
        except Exception as e:
            logger.error(f"Failed to delete instruments.csv: {e}")

    # 3. Clear Auth/Sessions
    if os.path.exists(SESSION_DIR):
        try:
            shutil.rmtree(SESSION_DIR)
            os.makedirs(SESSION_DIR)
            logger.info(f"Purged and recreated session directory: {SESSION_DIR}")
        except Exception as e:
             logger.error(f"Failed to purge session directory: {e}")
    else:
        os.makedirs(SESSION_DIR, exist_ok=True)
        logger.info(f"Created session directory: {SESSION_DIR}")

def check_auth():
    logger.info("Running Authentication Health Check...")
    script_path = os.path.join(repo_root, 'openalgo/scripts/authentication_health_check.py')

    if not os.path.exists(script_path):
        logger.warning(f"Auth check script not found at {script_path}. Skipping.")
        return

    try:
        # Run the health check script
        # We need to capture output to detect if login is required
        # Note: authentication_health_check.py prints to stdout

        # Use the same python interpreter
        cmd = [sys.executable, script_path]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout
        # logger.info(f"Auth Check Output:\n{output}")

        # Check for specific failure indicators in the output
        if "LOGIN REQUIRED" in output or "Token Invalid" in output or "Missing" in output:
             # But wait, authentication_health_check.py prints "Manual Actions Required"
             pass

        # Also check return code (though authentication_health_check might return 0 even if tokens missing)

        # For strict daily prep:
        # If we see "Token Invalid" or "Expired", we should fail.

        failed = False
        if "Token Invalid" in output or "Expired" in output or "Missing" in output:
             logger.error("Authentication Tokens are Invalid, Expired or Missing.")
             failed = True

        if result.returncode != 0:
            logger.error("Authentication check script failed.")
            failed = True

        if failed:
            print("\n" + "="*50)
            print("🔴 AUTHENTICATION REQUIRED")
            print("Please log in to OpenAlgo and Broker.")
            print("Run: openalgo/scripts/authentication_health_check.py for details.")
            print("="*50 + "\n")
            sys.exit(1)
        else:
            logger.info("Authentication check passed.")

    except Exception as e:
        logger.error(f"Failed to run auth check: {e}")
        sys.exit(1)

def fetch_instruments(mock=False, offline=False):
    logger.info("Fetching Instruments...")
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, 'instruments.csv')

    if mock:
        logger.warning("⚠️ USING MOCK DATA (Testing Mode)")
        generate_mock_instruments(csv_path)
        return

    if offline:
        logger.warning("⚠️ OFFLINE MODE: Skipping instrument fetch. Assuming instruments.csv exists or validation will fail.")
        if not os.path.exists(csv_path):
             logger.error("Offline mode but instruments.csv not found!")
             sys.exit(1)
        return

    api_key = os.getenv('OPENALGO_APIKEY')
    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

    try:
        url = f"{host}/api/v1/instruments"
        logger.info(f"Requesting {url}...")
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers={'X-API-KEY': api_key})
            if resp.status_code == 200:
                with open(csv_path, 'wb') as f:
                    f.write(resp.content)
                logger.info("Instruments downloaded successfully via API.")
            else:
                logger.error(f"Failed to fetch instruments from API: {resp.status_code}")
                sys.exit(1)
    except Exception as e:
        logger.error(f"API Connection failed: {e}")
        logger.error("Ensure OpenAlgo server is running on " + host)
        sys.exit(1)

def generate_mock_instruments(csv_path):
    now = datetime.now()

    # Calculate next Thursday for Weekly Expiry
    days_ahead = 3 - now.weekday()
    if days_ahead < 0: days_ahead += 7
    next_thursday = now + timedelta(days=days_ahead)

    # Calculate Monthly Expiry (Last Thursday)
    import calendar
    last_day = calendar.monthrange(now.year, now.month)[1]
    month_end = datetime(now.year, now.month, last_day)
    offset = (month_end.weekday() - 3) % 7
    monthly_expiry = month_end - timedelta(days=offset)

    data = [
        {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
        {'exchange': 'NSE', 'token': '2', 'symbol': 'NIFTY', 'name': 'NIFTY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},

        # MCX
        {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMIC23NOV', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 1, 'instrument_type': 'FUT'},
        {'exchange': 'MCX', 'token': '5', 'symbol': 'SILVER23NOV', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 30, 'instrument_type': 'FUT'},

        # NSE Futures
        {'exchange': 'NFO', 'token': '7', 'symbol': 'NIFTY23OCTFUT', 'name': 'NIFTY', 'expiry': monthly_expiry.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'FUT'},

        # NSE Options
        {'exchange': 'NFO', 'token': '10', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
        {'exchange': 'NFO', 'token': '11', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
    ]
    pd.DataFrame(data).to_csv(csv_path, index=False)
    logger.info(f"Mock instruments generated at {csv_path}")

def validate_symbols():
    logger.info("Validating Strategy Symbols...")
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"Config file not found: {CONFIG_FILE}. Skipping validation.")
        return

    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
            if not content.strip():
                configs = {}
            else:
                configs = json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    if not configs:
         logger.info("No active strategies configured.")
         return

    resolver = SymbolResolver(os.path.join(DATA_DIR, 'instruments.csv'))

    valid_count = 0
    invalid_count = 0

    print("\n--- SYMBOL VALIDATION REPORT ---")
    print(f"{'STRATEGY':<25} | {'TYPE':<8} | {'INPUT':<15} | {'RESOLVED':<30} | {'STATUS'}")
    print("-" * 95)

    for strat_id, config in configs.items():
        try:
            resolved = resolver.resolve(config)

            status = "✅ Valid"
            resolved_str = "Unknown"

            if resolved is None:
                status = "🔴 Invalid"
                invalid_count += 1
                resolved_str = "None"
            elif isinstance(resolved, dict):
                # Options return dict
                if resolved.get('status') == 'valid':
                    resolved_str = f"Expiry: {resolved.get('expiry')}"
                    valid_count += 1
                else:
                    status = "🔴 Invalid"
                    invalid_count += 1
                    resolved_str = "Invalid"
            else:
                # String result
                resolved_str = str(resolved)
                valid_count += 1

            print(f"{strat_id:<25} | {config.get('type', 'N/A'):<8} | {(config.get('underlying') or config.get('symbol') or 'N/A'):<15} | {resolved_str[:30]:<30} | {status}")

        except Exception as e:
            logger.error(f"Error validating {strat_id}: {e}")
            invalid_count += 1
            print(f"{strat_id:<25} | {config.get('type', 'N/A'):<8} | {(config.get('underlying') or config.get('symbol') or 'N/A'):<15} | {'ERROR':<30} | 🔴 Error")

    print("-" * 95)
    if invalid_count > 0:
        logger.error(f"Found {invalid_count} invalid symbols! Trading Halted.")
        sys.exit(1)
    else:
        logger.info("All symbols valid. Ready to trade.")

def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Daily Prep")
    parser.add_argument("--mock", action="store_true", help="Use mock data (Skip API)")
    parser.add_argument("--offline", action="store_true", help="Skip instrument fetch (Use existing)")
    parser.add_argument("--skip-auth", action="store_true", help="Skip auth check (Dev only)")
    args = parser.parse_args()

    print("🚀 DAILY PREP STARTED")

    check_env()
    purge_stale_state()

    if not args.skip_auth:
        check_auth()

    fetch_instruments(mock=args.mock, offline=args.offline)
    validate_symbols()

    print("✅ DAILY PREP COMPLETE")

if __name__ == "__main__":
    main()
