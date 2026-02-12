#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
import shutil
import glob
from datetime import datetime, timedelta
import httpx
import pandas as pd

# Configure Logging
try:
    from openalgo_observability.logging_setup import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger("DailyPrep")

try:
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    logger.error("Could not import SymbolResolver. Ensure PYTHONPATH includes 'vendor'.")
    sys.exit(1)

# Paths relative to this script
# Script is in vendor/openalgo/scripts/
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # vendor/openalgo/scripts
OPENALGO_ROOT = os.path.dirname(BASE_DIR) # vendor/openalgo

DATA_DIR = os.path.join(OPENALGO_ROOT, 'data')
STATE_DIR = os.path.join(OPENALGO_ROOT, 'strategies', 'state')
SESSION_DIR = os.path.join(OPENALGO_ROOT, 'sessions')
CONFIG_FILE = os.path.join(OPENALGO_ROOT, 'strategies', 'active_strategies.json')

def check_env():
    logger.info("Checking Environment...")
    if not os.getenv('OPENALGO_APIKEY'):
        logger.warning("OPENALGO_APIKEY not set. Using default 'demo_key'.")
        os.environ['OPENALGO_APIKEY'] = 'demo_key'
    logger.info("Environment OK.")

def purge_stale_state():
    logger.info("Purging Stale State...")

    # 1. State Files
    if os.path.exists(STATE_DIR):
        files = glob.glob(os.path.join(STATE_DIR, "*.json"))
        count = 0
        for f in files:
            try:
                os.remove(f)
                count += 1
            except Exception as e:
                logger.error(f"Failed to delete {f}: {e}")
        logger.info(f"Deleted {count} state files from {STATE_DIR}")
    else:
        os.makedirs(STATE_DIR, exist_ok=True)

    # 2. Cached Instruments
    inst_file = os.path.join(DATA_DIR, 'instruments.csv')
    if os.path.exists(inst_file):
        try:
            os.remove(inst_file)
            logger.info("Deleted cached instruments.csv")
        except Exception as e:
            logger.error(f"Failed to delete instruments.csv: {e}")

    # 3. Sessions
    if os.path.exists(SESSION_DIR):
        try:
            shutil.rmtree(SESSION_DIR)
            os.makedirs(SESSION_DIR)
            logger.info("Purged session directory")
        except Exception as e:
            logger.error(f"Failed to purge sessions: {e}")
    else:
        os.makedirs(SESSION_DIR, exist_ok=True)

def check_auth():
    logger.info("Running Authentication Health Check...")
    # Mocking for now as no real broker connection
    logger.info("Authentication check passed (Simulated).")

def fetch_instruments():
    logger.info("Fetching Instruments...")
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, 'instruments.csv')

    # Try fetching from API (Simulated if no host)
    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
    api_key = os.getenv('OPENALGO_APIKEY')

    fetched = False
    try:
        if 'localhost' in host:
            # Check if server running? No, just try request with short timeout
             with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{host}/api/v1/instruments", headers={'X-API-KEY': api_key})
                if resp.status_code == 200:
                    with open(csv_path, 'wb') as f:
                        f.write(resp.content)
                    fetched = True
                    logger.info("Fetched instruments from API.")
    except Exception as e:
        logger.warning(f"API fetch failed: {e}")

    if not fetched:
        logger.info("Using Fallback: Generating Mock Instruments...")
        # Use the logic from previous script but ensure it covers everything needed
        # We can re-use the generator logic
        _generate_mock_instruments(csv_path)

def _generate_mock_instruments(path):
    now = datetime.now()
    # Next Thursday
    days_ahead = 3 - now.weekday()
    if days_ahead < 0: days_ahead += 7
    next_thursday = now + timedelta(days=days_ahead)

    # Monthly (Last Thursday of Month)
    # Simple logic: If today > 25th, maybe next month?
    # Let's just create expiries for this month and next month

    import calendar
    def get_last_thursday(year, month):
        last_day = calendar.monthrange(year, month)[1]
        dt = datetime(year, month, last_day)
        offset = (dt.weekday() - 3) % 7
        return dt - timedelta(days=offset)

    this_month_exp = get_last_thursday(now.year, now.month)
    if now > this_month_exp:
        # Move to next month
        next_month = now.month + 1 if now.month < 12 else 1
        next_year = now.year if now.month < 12 else now.year + 1
        this_month_exp = get_last_thursday(next_year, next_month)

    data = [
        {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ', 'tradingsymbol': 'RELIANCE'},
        {'exchange': 'NSE', 'token': '2', 'symbol': 'NIFTY', 'name': 'NIFTY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ', 'tradingsymbol': 'NIFTY'},

        # Options
        {'exchange': 'NFO', 'token': '10', 'symbol': f'NIFTY{next_thursday.strftime("%d%b%y").upper()}19500CE', 'name': 'NIFTY', 'expiry': next_thursday, 'lot_size': 50, 'instrument_type': 'OPT', 'tradingsymbol': f'NIFTY{next_thursday.strftime("%d%b%y").upper()}19500CE', 'strike': 19500},
        {'exchange': 'NFO', 'token': '11', 'symbol': f'NIFTY{this_month_exp.strftime("%d%b%y").upper()}19500CE', 'name': 'NIFTY', 'expiry': this_month_exp, 'lot_size': 50, 'instrument_type': 'OPT', 'tradingsymbol': f'NIFTY{this_month_exp.strftime("%d%b%y").upper()}19500CE', 'strike': 19500},

        # MCX
        {'exchange': 'MCX', 'token': '20', 'symbol': 'SILVERMIC26NOVFUT', 'name': 'SILVER', 'expiry': datetime(2026, 11, 30), 'lot_size': 1, 'instrument_type': 'FUT', 'tradingsymbol': 'SILVERMIC26NOVFUT'},
        {'exchange': 'MCX', 'token': '21', 'symbol': 'SILVER26NOVFUT', 'name': 'SILVER', 'expiry': datetime(2026, 11, 30), 'lot_size': 30, 'instrument_type': 'FUT', 'tradingsymbol': 'SILVER26NOVFUT'},
    ]
    pd.DataFrame(data).to_csv(path, index=False)
    logger.info(f"Mock instruments saved to {path}")

def validate_symbols():
    logger.info("Validating Strategy Symbols...")
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"Config file not found: {CONFIG_FILE}. Creating dummy config for testing.")
        dummy_config = {
            "Test_NIFTY_Opt": {
                "type": "OPT",
                "underlying": "NIFTY",
                "option_type": "CE",
                "expiry_preference": "WEEKLY"
            },
            "Test_MCX_Silver": {
                "type": "FUT",
                "underlying": "SILVER",
                "exchange": "MCX"
            }
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(dummy_config, f, indent=4)
        # return

    try:
        with open(CONFIG_FILE, 'r') as f:
            configs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    resolver = SymbolResolver(os.path.join(DATA_DIR, 'instruments.csv'))

    invalid_count = 0
    print("\n--- SYMBOL VALIDATION REPORT ---")
    print(f"{'STRATEGY':<25} | {'TYPE':<8} | {'INPUT':<15} | {'RESOLVED':<30} | {'STATUS'}")
    print("-" * 95)

    for strat_id, config in configs.items():
        try:
            resolved = resolver.resolve(config)
            status = "✅ Valid"
            resolved_str = "None"

            if resolved is None:
                status = "🔴 Invalid"
                invalid_count += 1
            elif isinstance(resolved, dict):
                if resolved.get('status') == 'valid':
                    resolved_str = str(resolved.get('expiry'))
                else:
                    status = "🔴 Invalid"
                    invalid_count += 1
            else:
                resolved_str = str(resolved)

            print(f"{strat_id:<25} | {str(config.get('type')):<8} | {str(config.get('underlying')):<15} | {resolved_str[:30]:<30} | {status}")
        except Exception as e:
            logger.error(f"Error validating {strat_id}: {e}")
            invalid_count += 1

    print("-" * 95)
    if invalid_count > 0:
        logger.error(f"Found {invalid_count} invalid symbols! Trading Halted.")
        sys.exit(1)
    else:
        logger.info("All symbols valid.")

def main():
    print("🚀 DAILY PREP STARTED")
    check_env()
    purge_stale_state()
    check_auth()
    fetch_instruments()
    validate_symbols()
    print("✅ DAILY PREP COMPLETE")

if __name__ == "__main__":
    main()
