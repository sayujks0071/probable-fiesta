#!/usr/bin/env python3
import os
import sys
import json
import logging
import shutil
import glob
from datetime import datetime
import pandas as pd

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import Utils
try:
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    from openalgo.strategies.utils.trading_utils import APIClient
except ImportError:
    # If openalgo is in vendor/openalgo and PYTHONPATH is set correctly, this should work.
    # If not, try appending vendor/openalgo
    vendor_path = os.path.join(repo_root, 'vendor', 'openalgo')
    sys.path.append(vendor_path)
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    from openalgo.strategies.utils.trading_utils import APIClient

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyPrep")

DATA_DIR = os.path.join(repo_root, 'openalgo/data')
SESSION_DIR = os.path.join(repo_root, 'openalgo/sessions') # Verify if this is the correct session dir
STRATEGY_CONFIG = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')

def check_env():
    logger.info("1. Environment Checks")
    api_key = os.getenv('OPENALGO_APIKEY')
    if not api_key:
        logger.error("❌ OPENALGO_APIKEY not set!")
        sys.exit(1)

    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
    logger.info(f"   API Key: {'*' * 5}{api_key[-4:] if len(api_key)>4 else '****'}")
    logger.info(f"   Host: {host}")

def purge_stale_state():
    logger.info("2. Purging Stale State")

    # Clear Session Cache
    # Note: Flask sessions might be in 'instance/flask_session' or similar depending on config.
    # Assuming 'openalgo/sessions' is the target based on previous script.
    if os.path.exists(SESSION_DIR):
        try:
            shutil.rmtree(SESSION_DIR)
            os.makedirs(SESSION_DIR)
            logger.info(f"   ✅ Purged {SESSION_DIR}")
        except Exception as e:
            logger.error(f"   ❌ Failed to purge sessions: {e}")
    else:
        logger.info(f"   ℹ️ Session dir {SESSION_DIR} not found (ok).")

    # Clear Cached Instruments
    inst_file = os.path.join(DATA_DIR, 'instruments.csv')
    if os.path.exists(inst_file):
        try:
            os.remove(inst_file)
            logger.info("   ✅ Deleted cached instruments.csv")
        except Exception as e:
            logger.error(f"   ❌ Failed to delete instruments.csv: {e}")

def check_login():
    logger.info("3. Login & Connectivity Check")
    api_key = os.getenv('OPENALGO_APIKEY')
    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

    client = APIClient(api_key=api_key, host=host)

    # Try to fetch a quote or profile to verify auth
    # APIClient doesn't have 'get_profile', but 'get_quote' for NIFTY is a good test.
    # Or 'get_instruments' which we need anyway.

    logger.info(f"   Connecting to {host}...")
    try:
        # We try to fetch NIFTY quote. If 401/403, we know auth failed.
        quote = client.get_quote("NIFTY 50", exchange="NSE", max_retries=1)

        # Note: get_quote returns None on failure, need to check logs/implementation if it raises exception on 401.
        # Looking at APIClient implementation, it catches exceptions and logs errors.
        # We can't distinguish 401 from other errors easily unless we modify APIClient or check logs.
        # But for 'Daily Prep', if we can't get data, we stop.

        if quote is None:
             # Try another check? Instruments?
             pass
        else:
             logger.info("   ✅ Auth Valid (Quote Fetch Success)")
             return client

    except Exception as e:
        logger.error(f"   ❌ Connectivity Error: {e}")

    # If quote failed, let's try instruments fetch in next step, but ideally we fail fast here.
    # Since APIClient suppresses exceptions, we might proceed to Step 4 and fail there.
    return client

def fetch_instruments(client):
    logger.info("4. Refreshing Instruments")
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, 'instruments.csv')

    df = client.get_instruments(exchange="NSE", max_retries=3)
    if df.empty:
        logger.error("   ❌ Failed to fetch NSE instruments (Empty response or Auth failed).")
        # Try MCX too?
    else:
        logger.info(f"   ✅ Fetched {len(df)} NSE instruments.")

    # Fetch MCX
    df_mcx = client.get_instruments(exchange="MCX", max_retries=3)
    if not df_mcx.empty:
         logger.info(f"   ✅ Fetched {len(df_mcx)} MCX instruments.")
         df = pd.concat([df, df_mcx], ignore_index=True)

    if df.empty:
        logger.error("   ❌ CRITICAL: Could not fetch any instruments. Login required or Server Down.")
        print("\n!!! ACTION REQUIRED: PLEASE LOGIN TO OPENALGO !!!\n")
        sys.exit(1)

    # Save
    try:
        df.to_csv(csv_path, index=False)
        logger.info(f"   ✅ Saved {len(df)} instruments to {csv_path}")
    except Exception as e:
        logger.error(f"   ❌ Failed to save instruments: {e}")
        sys.exit(1)

def validate_symbols():
    logger.info("5. Symbol Validation")

    if not os.path.exists(STRATEGY_CONFIG):
        logger.warning(f"   ⚠️ No strategy config found at {STRATEGY_CONFIG}")
        return

    try:
        with open(STRATEGY_CONFIG, 'r') as f:
            content = f.read().strip()
            if not content:
                configs = {}
            else:
                configs = json.loads(content)
    except Exception as e:
        logger.error(f"   ❌ JSON Parse Error in {STRATEGY_CONFIG}: {e}")
        sys.exit(1)

    if not configs:
        logger.info("   ℹ️ No active strategies.")
        return

    resolver = SymbolResolver() # Uses default path (which we just updated)

    failures = []

    print("\n" + "="*80)
    print(f"{'STRATEGY':<20} | {'TYPE':<6} | {'INPUT':<15} | {'RESOLVED':<25} | {'STATUS'}")
    print("-" * 80)

    for name, cfg in configs.items():
        try:
            # Resolve
            # If cfg has 'symbol' but no 'underlying', assume 'symbol' is underlying if not found?
            # SymbolResolver logic handles 'underlying' or 'symbol'.

            # For validation, we want to ensure we can resolve to a TRADABLE symbol.
            # SymbolResolver.resolve returns valid symbol string or validation dict (for options).

            # Use get_tradable_symbol with a dummy spot price for Options check?
            # Or just resolve() for validity.

            res = resolver.resolve(cfg)

            status = "✅ OK"
            res_str = str(res)

            if res is None:
                status = "❌ INVALID"
                failures.append(name)
            elif isinstance(res, dict):
                # Options validation dict
                if res.get('status') == 'valid':
                    res_str = f"Expiry: {res.get('expiry')}"
                else:
                    status = "❌ INVALID"
                    failures.append(name)

            print(f"{name:<20} | {cfg.get('type','EQ'):<6} | {cfg.get('underlying', cfg.get('symbol','?')):<15} | {res_str[:25]:<25} | {status}")

        except Exception as e:
            logger.error(f"Error validating {name}: {e}")
            failures.append(name)
            print(f"{name:<20} | {cfg.get('type','?'):<6} | {'ERROR':<15} | {'-':<25} | ❌ ERROR")

    print("="*80 + "\n")

    if failures:
        logger.error(f"   ❌ Validation Failed for {len(failures)} strategies: {failures}")
        logger.error("   ⛔ TRADING HALTED. Fix symbols in active_strategies.json")
        sys.exit(1)
    else:
        logger.info("   ✅ All Symbols Validated.")

def main():
    print("\n🚀 OPENALGO DAILY PREP STARTED\n")
    check_env()
    purge_stale_state()
    client = check_login()
    fetch_instruments(client)
    validate_symbols()
    print("\n✅ PREP COMPLETE - SYSTEM READY FOR TRADING\n")

if __name__ == "__main__":
    main()
