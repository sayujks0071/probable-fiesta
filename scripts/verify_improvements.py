#!/usr/bin/env python3
"""
Verify Improvements Script
Runs backtests on Original vs V2 strategies using local yfinance data.
"""
import os
import sys
import logging
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import importlib.util

# Setup paths
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(repo_root)
sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))

# Mock API Client for Local Backtesting
class LocalAPIClient:
    def __init__(self):
        self.host = "LOCAL"

    def history(self, symbol, exchange="NSE", interval="15m", start_date=None, end_date=None):
        # Map symbols
        yf_symbol = symbol
        if symbol == "NIFTY": yf_symbol = "^NSEI"
        elif symbol == "BANKNIFTY": yf_symbol = "^NSEBANK"
        elif symbol == "INDIA VIX": yf_symbol = "^INDIAVIX"
        elif not symbol.endswith(".NS") and not symbol.startswith("^"):
            yf_symbol = f"{symbol}.NS"

        # Interval mapping
        # yfinance supports 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        if interval == "day": interval = "1d"
        # Force 60m if 15m requested to avoid limitation
        if interval == "15m": interval = "60m"

        try:
            # yfinance download
            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=interval, progress=False)
            if df.empty:
                return pd.DataFrame()

            # Flatten MultiIndex if present (yfinance v0.2+)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Standardize columns
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume"
            })
            df.index.name = "datetime"

            # Ensure columns exist
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col not in df.columns:
                    df[col] = 0.0

            return df
        except Exception as e:
            logging.error(f"YF Error for {symbol}: {e}")
            return pd.DataFrame()

# Import Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    try:
        from simple_backtest_engine import SimpleBacktestEngine
    except ImportError as e:
        print(f"Failed to import SimpleBacktestEngine: {e}")
        print(f"Sys Path: {sys.path}")
        sys.exit(1)

class LocalBacktestEngine(SimpleBacktestEngine):
    def __init__(self, initial_capital=100000.0):
        # Bypass parent init to avoid APIClient connection
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.client = LocalAPIClient() # Use local client
        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        self.metrics = {}

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Verifier")

STRATEGIES = [
    {
        "name": "ML_Momentum",
        "file_v1": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "file_v2": "openalgo/strategies/scripts/advanced_ml_momentum_strategy_v2.py",
        "symbols": ["NIFTY", "INFY"]
    },
    {
        "name": "AI_Hybrid",
        "file_v1": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "file_v2": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout_v2.py",
        "symbols": ["NIFTY", "SBIN"]
    },
    {
        "name": "SuperTrend_VWAP",
        "file_v1": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "file_v2": "openalgo/strategies/scripts/supertrend_vwap_strategy_v2.py",
        "symbols": ["NIFTY", "RELIANCE"]
    }
]

def load_module(filepath):
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return None

def run_tests():
    engine = LocalBacktestEngine()
    # Use fixed dates known to exist in Yahoo History (e.g., late 2024)
    # 60 days range
    start_date = "2024-09-01"
    end_date = "2024-11-01"

    print(f"{'Strategy':<20} | {'Ver':<3} | {'Symbol':<10} | {'Sharpe':<6} | {'Ret %':<7} | {'DD %':<6} | {'Trades':<6}")
    print("-" * 80)

    for strat in STRATEGIES:
        for ver, file_key in [("V1", "file_v1"), ("V2", "file_v2")]:
            module = load_module(strat[file_key])
            if not module: continue

            for symbol in strat['symbols']:
                try:
                    res = engine.run_backtest(
                        strategy_module=module,
                        symbol=symbol,
                        exchange="NSE",
                        start_date=start_date,
                        end_date=end_date,
                        interval="15m" # Will be mapped to 60m by LocalAPIClient
                    )

                    metrics = res.get('metrics', {})
                    sharpe = metrics.get('sharpe_ratio', 0)
                    ret = metrics.get('total_return_pct', 0)
                    dd = metrics.get('max_drawdown_pct', 0)
                    trades = res.get('total_trades', 0)

                    print(f"{strat['name']:<20} | {ver:<3} | {symbol:<10} | {sharpe:6.2f} | {ret:7.2f} | {dd:6.2f} | {trades:6}")

                except Exception as e:
                    logger.error(f"Error {strat['name']} {ver} {symbol}: {e}")

if __name__ == "__main__":
    run_tests()
