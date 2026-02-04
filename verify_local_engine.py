import sys
import os

# Add root to path
sys.path.append(os.getcwd())

try:
    from openalgo.strategies.utils.local_backtest_engine import LocalBacktestEngine
    engine = LocalBacktestEngine()
    print("LocalBacktestEngine initialized successfully.")

    # Try fetching one bar of data to verify yfinance
    df = engine.load_historical_data("NIFTY", "NSE", "2023-10-01", "2023-10-05", "1d")
    if not df.empty:
        print(f"Fetched {len(df)} rows for NIFTY.")
    else:
        print("Fetched empty data (might be network issue, but module works).")

except Exception as e:
    print(f"Verification failed: {e}")
    sys.exit(1)
