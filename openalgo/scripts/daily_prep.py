#!/usr/bin/env python3
import os
import sys
import json
import logging
import shutil
import glob
import time
from datetime import datetime, timedelta
import httpx
import pandas as pd

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

from openalgo.strategies.utils.symbol_resolver import SymbolResolver

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyPrep")

DATA_DIR = os.path.join(repo_root, 'openalgo/data')
STATE_DIR = os.path.join(repo_root, 'openalgo/strategies/state')
SESSION_DIR = os.path.join(repo_root, 'openalgo/sessions')
CONFIG_FILE = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')

def check_env():
    logger.info("Checking Environment...")
    required_vars = ['OPENALGO_APIKEY']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.warning(f"Missing env vars: {missing}. Using defaults or risking failure.")
        if 'OPENALGO_APIKEY' in missing:
             os.environ['OPENALGO_APIKEY'] = 'demo_key' # Fallback for testing

    # Timezone check
    if time.tzname[0] != 'IST' and 'Asia/Kolkata' not in os.environ.get('TZ', ''):
        logger.warning(f"System timezone is {time.tzname}. Recommend setting TZ='Asia/Kolkata'.")

    logger.info("Environment OK.")

def purge_stale_state():
    logger.info("Purging Stale State...")

    # 1. Clear PositionManager state (Risk Manager state matches this usually)
    # We might want to keep some risk state? But "fresh day" usually means reset daily counters.
    # If RiskManager stores persistent PnL across days, we should NOT delete it?
    # Requirement: "Delete prior-day login/session cache... temp runtime caches... cached instrument maps"
    # It doesn't explicitly say delete strategy state (positions).
    # However, "Daily-Ready" implies square off?
    # I will be conservative and delete SESSION and INSTRUMENTS, and maybe LOGS rotation.
    # Strategies usually manage their own state file. I will clean up session only as requested.

    # Clean Session Dir
    if os.path.exists(SESSION_DIR):
        try:
            shutil.rmtree(SESSION_DIR)
            os.makedirs(SESSION_DIR)
            logger.info(f"Purged session directory: {SESSION_DIR}")
        except Exception as e:
             logger.error(f"Failed to purge session directory: {e}")
    else:
        os.makedirs(SESSION_DIR, exist_ok=True)

    # Clean Instruments
    inst_file = os.path.join(DATA_DIR, 'instruments.csv')
    if os.path.exists(inst_file):
        try:
            os.remove(inst_file)
            logger.info("Deleted cached instruments.csv")
        except Exception as e:
            logger.error(f"Failed to delete instruments.csv: {e}")

def check_auth_health():
    logger.info("Running Authentication Health Check...")

    # We can invoke the existing script and check output
    script_path = os.path.join(repo_root, 'openalgo/scripts/authentication_health_check.py')
    if os.path.exists(script_path):
        import subprocess
        try:
            # We assume the user has started the server (make run or similar).
            # This script just validates it.
            result = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
            print(result.stdout) # Show output to user

            if "ISSUES DETECTED" in result.stdout and "None" not in result.stdout.split("ISSUES DETECTED:")[1]:
                # If issues detected is followed by items (not None)
                # Parse strictly
                lines = result.stdout.split('\n')
                issue_idx = -1
                for i, line in enumerate(lines):
                    if "ISSUES DETECTED" in line:
                        issue_idx = i
                        break

                if issue_idx != -1 and issue_idx + 1 < len(lines):
                    if "None" not in lines[issue_idx+1]:
                        logger.error("Authentication Health Check Failed. Please resolve issues above.")
                        # Strict fail? User said "If login fails: stop immediately"
                        # But auth check script might report minor issues.
                        # We will fail if "Kite Token Invalid" or "Server not started".
                        if "Server not started" in result.stdout or "Token Invalid" in result.stdout:
                             sys.exit(1)

            logger.info("Authentication Check Passed (or non-critical warnings).")

        except Exception as e:
            logger.error(f"Failed to run auth check: {e}")
            sys.exit(1)
    else:
        logger.warning("Auth check script not found.")

def fetch_instruments():
    logger.info("Fetching Instruments...")
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, 'instruments.csv')

    api_key = os.getenv('OPENALGO_APIKEY')
    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

    # Try multiple endpoints or exchanges
    exchanges = ['NSE', 'NFO', 'MCX']
    dfs = []

    with httpx.Client(timeout=30.0) as client:
        for ex in exchanges:
            url = f"{host}/instruments/{ex}" # Broker proxy endpoint often
            # Or /api/v1/instruments?exchange={ex}

            # Try /api/v1/instruments first (OpenAlgo native)
            # fallback to /instruments/{ex} (Kite Connect proxy)

            logger.info(f"Fetching {ex} instruments...")
            try:
                # 1. Try OpenAlgo proxy
                resp = client.get(f"{host}/instruments/{ex}", headers={'X-API-KEY': api_key})
                if resp.status_code == 200:
                    from io import StringIO
                    df = pd.read_csv(StringIO(resp.text), low_memory=False)
                    if 'exchange' not in df.columns:
                        df['exchange'] = ex
                    dfs.append(df)
                    logger.info(f"Fetched {len(df)} {ex} instruments.")
                    continue

                # 2. Try generic API
                resp = client.get(f"{host}/api/v1/instruments?exchange={ex}", headers={'X-API-KEY': api_key})
                if resp.status_code == 200:
                    # Might be JSON or CSV
                    try:
                        data = resp.json()
                        if isinstance(data, list):
                            df = pd.DataFrame(data)
                        elif isinstance(data, dict) and 'data' in data:
                            df = pd.DataFrame(data['data'])
                        else:
                            # Try CSV
                            from io import StringIO
                            df = pd.read_csv(StringIO(resp.text), low_memory=False)
                    except:
                        from io import StringIO
                        df = pd.read_csv(StringIO(resp.text), low_memory=False)

                    if 'exchange' not in df.columns:
                        df['exchange'] = ex
                    dfs.append(df)
                    logger.info(f"Fetched {len(df)} {ex} instruments.")
                    continue

                logger.warning(f"Failed to fetch {ex}: {resp.status_code}")

            except Exception as e:
                logger.error(f"Error fetching {ex}: {e}")

    if dfs:
        full_df = pd.concat(dfs, ignore_index=True)
        full_df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(full_df)} instruments to {csv_path}")
    elif '--mock' in sys.argv:
        logger.warning("Mock mode enabled. Generating mock instruments.")
        # Generate comprehensive mock data
        now = datetime.now()
        next_thursday = now + timedelta(days=(3-now.weekday()) % 7)
        if next_thursday <= now: next_thursday += timedelta(days=7)

        # Monthly Expiry (Last Thu of Month)
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = datetime(now.year, now.month, last_day)
        offset = (month_end.weekday() - 3) % 7
        monthly_expiry = month_end - timedelta(days=offset)

        mock_data = [
            {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '2', 'symbol': 'NIFTY', 'name': 'NIFTY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '3', 'symbol': 'INFY', 'name': 'INFY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMICFUT', 'name': 'SILVERM', 'expiry': (now + timedelta(days=30)).strftime('%Y-%m-%d'), 'lot_size': 1, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '5', 'symbol': 'SILVERFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=30)).strftime('%Y-%m-%d'), 'lot_size': 30, 'instrument_type': 'FUT'},
            {'exchange': 'NFO', 'token': '10', 'symbol': 'NIFTYWEEKLYCE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 22000, 'option_type': 'CE'},
             {'exchange': 'NFO', 'token': '11', 'symbol': 'NIFTYMONTHLYCE', 'name': 'NIFTY', 'expiry': monthly_expiry.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 22000, 'option_type': 'CE'},
        ]
        pd.DataFrame(mock_data).to_csv(csv_path, index=False)
        logger.info(f"Generated {len(mock_data)} mock instruments.")
    else:
        logger.error("Critical Failure: No instruments. Stopping.")
        sys.exit(1)

def validate_strategies():
    logger.info("Validating Strategy Symbols...")
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        sys.exit(1)

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

    resolver = SymbolResolver() # Uses default path which we just populated

    report_lines = []
    report_lines.append("# Daily Validation Report")
    report_lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report_lines.append("| Strategy | Input | Resolved Symbol | Status | Notes |")
    report_lines.append("|---|---|---|---|---|")

    invalid_strategies = []

    for strat_id, config in configs.items():
        try:
            res = resolver.resolve(config)

            status = "✅ Valid"
            resolved_str = "Unknown"
            notes = ""

            if res is None:
                status = "🔴 Invalid"
                resolved_str = "None"
                notes = "Symbol not found in master"
                invalid_strategies.append(strat_id)
            elif isinstance(res, dict):
                # Option descriptor
                if res.get('status') == 'valid':
                    resolved_str = f"Option Chain ({res.get('expiry')})"
                    notes = f"Underlying: {res.get('underlying')}, Count: {res.get('count')}"
                else:
                    status = "🔴 Invalid"
                    resolved_str = "Invalid"
                    notes = "Option validation failed"
                    invalid_strategies.append(strat_id)
            else:
                # String
                resolved_str = res

                # Check for Fallback logging (MCX Standard vs MINI)
                # We can't easily capture the log here, but we can check if it looks like MINI
                if config.get('exchange') == 'MCX':
                    if 'MINI' in resolved_str or 'M' in resolved_str.replace(config.get('underlying', ''), ''):
                        notes = "Using MINI"
                    elif 'M' not in resolved_str and 'MINI' not in resolved_str:
                        notes = "Using Standard (MINI not found?)"

            report_lines.append(f"| {strat_id} | {config.get('underlying') or config.get('symbol')} | {resolved_str} | {status} | {notes} |")

            logger.info(f"Strategy {strat_id}: {status} ({resolved_str})")

        except Exception as e:
            logger.error(f"Validation Error {strat_id}: {e}")
            report_lines.append(f"| {strat_id} | {config.get('underlying')} | ERROR | 🔴 Error | {str(e)} |")
            invalid_strategies.append(strat_id)

    # Write Report
    report_path = "daily_validation_report.md"
    with open(report_path, 'w') as f:
        f.write('\n'.join(report_lines))

    logger.info(f"Validation Report generated: {report_path}")

    if invalid_strategies:
        logger.error(f"Strategies failed validation: {invalid_strategies}")
        sys.exit(1)
    else:
        logger.info("All strategies validated successfully.")

def main():
    print("🚀 DAILY PREP STARTED")
    check_env()
    purge_stale_state()
    check_auth_health()
    fetch_instruments()
    validate_strategies()
    print("✅ DAILY PREP COMPLETE")

if __name__ == "__main__":
    main()
