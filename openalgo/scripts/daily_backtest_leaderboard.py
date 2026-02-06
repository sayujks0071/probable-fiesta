#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import importlib.util
import time

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import Backtest Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    import openalgo.strategies.utils.simple_backtest_engine as sbe
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine
    import simple_backtest_engine as sbe

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

# --- Mock API Client ---
class MockAPIClient:
    def __init__(self, api_key=None, host=None):
        self.api_key = api_key
        self.host = host
        self.logger = logging.getLogger("MockAPI")

    def history(self, symbol, exchange="NSE", interval="15m", start_date=None, end_date=None, max_retries=3):
        # Map Symbol to Yahoo Finance Ticker
        ticker_map = {
            "NIFTY": "NIFTYBEES.NS", # Use ETF for Volume data
            "BANKNIFTY": "BANKBEES.NS", # Use ETF for Volume data
            "INDIA VIX": "^INDIAVIX",
            "SILVERMIC": "SI=F", # Silver Futures (Global Proxy)
            "GOLDM": "GC=F", # Gold Futures (Global Proxy)
            "CRUDEOIL": "CL=F", # Crude Oil (Global Proxy)
            "NATURALGAS": "NG=F", # Natural Gas (Global Proxy)
        }

        # Default for stocks: append .NS
        ticker = ticker_map.get(symbol, f"{symbol}.NS" if exchange in ["NSE", "NSE_INDEX"] else symbol)

        # Handle interval mapping
        # yfinance supports: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        yf_interval = interval
        if interval == "day": yf_interval = "1d"

        try:
            self.logger.info(f"Fetching {ticker} ({interval}) from {start_date} to {end_date}")
            df = yf.download(ticker, start=start_date, end=end_date, interval=yf_interval, progress=False)

            if df.empty:
                self.logger.warning(f"No data for {ticker}")
                return pd.DataFrame()

            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename columns to lowercase
            df.columns = [c.lower() for c in df.columns]

            # Ensure required columns
            required = ['open', 'high', 'low', 'close', 'volume']
            for col in required:
                if col not in df.columns:
                    df[col] = 0.0

            # Reset index to get datetime/timestamp column if it's the index
            # SimpleBacktestEngine expects index to be datetime or 'datetime' column
            # yfinance returns DatetimeIndex, which is good.

            return df

        except Exception as e:
            self.logger.error(f"Error fetching {ticker}: {e}")
            return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE"):
        # Mock quote for VIX etc.
        if symbol == "INDIA VIX":
             # Return dummy VIX
             return {'ltp': 15.0}
        return {'ltp': 100.0}

# Monkey Patch
sbe.APIClient = MockAPIClient

# --- Configuration ---

STRATEGIES = [
    {
        "name": "SuperTrend_VWAP",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "MCX_Momentum",
        "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
        "symbol": "SILVERMIC",
        "exchange": "MCX",
        "params": {"min_atr": 0.05} # Adjusted for SI=F (USD)
    },
    {
        "name": "AI_Hybrid",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    }
]

# Tuning Grid
TUNING_CONFIG = {
    "SuperTrend_VWAP": {
        "vol_multiplier": [0.5, 1.0],
        "adx_threshold": [15, 20]
    },
    "MCX_Momentum": {
        "adx_threshold": [20, 25]
    },
    "AI_Hybrid": {
        "rsi_lower": [30, 40],
        "rsi_upper": [55, 60]
    },
    "ML_Momentum": {
        "threshold": [0.003, 0.005],
        "vol_multiplier": [0.2]
    }
}

def load_strategy_module(filepath):
    """Load a strategy script as a module."""
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        # Check if file exists
        full_path = os.path.join(repo_root, filepath)
        if not os.path.exists(full_path):
             logger.error(f"File not found: {full_path}")
             return None

        spec = importlib.util.spec_from_file_location(module_name, full_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def run_leaderboard():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    # 180 Days Backtest
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    results = []

    for strat_config in STRATEGIES:
        logger.info(f"Backtesting {strat_config['name']}...")

        module = load_strategy_module(strat_config['file'])
        if not module:
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"Strategy {strat_config['name']} does not have 'generate_signal' function. Skipping.")
            continue

        # Determine variants to run
        base_params = strat_config.get('params', {})
        runs = [{"name": strat_config['name'], "params": base_params}]

        # Add variants from Tuning Config
        if strat_config['name'] in TUNING_CONFIG:
            grid = TUNING_CONFIG[strat_config['name']]
            import itertools
            keys = list(grid.keys())
            values = list(grid.values())
            combinations = list(itertools.product(*values))

            for i, combo in enumerate(combinations):
                variant_params = base_params.copy() if base_params else {}
                variant_params.update(dict(zip(keys, combo)))
                runs.append({
                    "name": f"{strat_config['name']}_v{i+1}",
                    "params": variant_params
                })

        for run in runs:
            logger.info(f"  > Variant: {run['name']} Params: {run['params']}")

            original_gen = module.generate_signal

            # Create a partial/wrapper
            params = run['params']

            # Wrapper to inject params
            def wrapped_gen(df, client=None, symbol=None):
                return original_gen(df, client, symbol, params=params)

            # Create a temporary object acting as module
            class ModuleWrapper:
                pass
            wrapper = ModuleWrapper()
            wrapper.generate_signal = wrapped_gen

            # Copy attributes (SL/TP multipliers) if they exist
            if hasattr(module, 'ATR_SL_MULTIPLIER'): wrapper.ATR_SL_MULTIPLIER = module.ATR_SL_MULTIPLIER
            if hasattr(module, 'ATR_TP_MULTIPLIER'): wrapper.ATR_TP_MULTIPLIER = module.ATR_TP_MULTIPLIER
            if hasattr(module, 'TIME_STOP_BARS'): wrapper.TIME_STOP_BARS = module.TIME_STOP_BARS
            if hasattr(module, 'BREAKEVEN_TRIGGER_R'): wrapper.BREAKEVEN_TRIGGER_R = module.BREAKEVEN_TRIGGER_R
            if hasattr(module, 'check_exit'): wrapper.check_exit = module.check_exit

            try:
                # Run Backtest
                res = engine.run_backtest(
                    strategy_module=wrapper,
                    symbol=strat_config['symbol'],
                    exchange=strat_config['exchange'],
                    start_date=start_str,
                    end_date=end_str,
                    interval="1h" # Use 1h for 180 days to be faster and less noise, or 15m?
                                  # yfinance 15m is limited to 60 days usually.
                                  # 1h is available for 730 days.
                )

                # NOTE: yfinance restriction: 15m data only last 60 days.
                # If we want 180 days, we must use 1h interval or accept 60 days.
                # Let's try 1h for stability or stick to 60 days 15m?
                # The user asked for "Sufficient trade count".
                # 60 days of 15m is ~1500 bars. 180 days of 1h is ~1200 bars.
                # Let's use 1h for longer horizon (Regime changes).

                if 'error' in res:
                    logger.error(f"Backtest failed for {run['name']}: {res['error']}")
                    continue

                metrics = res.get('metrics', {})
                results.append({
                    "strategy": run['name'],
                    "params": run['params'],
                    "total_return": metrics.get('total_return_pct', 0),
                    "sharpe": metrics.get('sharpe_ratio', 0),
                    "drawdown": metrics.get('max_drawdown_pct', 0),
                    "win_rate": metrics.get('win_rate', 0),
                    "trades": res.get('total_trades', 0),
                    "profit_factor": metrics.get('profit_factor', 0),
                    "total_profit": metrics.get('total_profit', 0),
                    "total_loss": metrics.get('total_loss', 0)
                })

            except Exception as e:
                logger.error(f"Error backtesting {run['name']}: {e}", exc_info=True)

    # Sort by Sharpe Ratio (Primary) then Return
    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    # Save JSON
    with open("leaderboard.json", "w") as f:
        json.dump(results, f, indent=4)

    # Generate Markdown
    md = "# Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md += f"**Period:** {start_str} to {end_str} (Interval: 1h)\n\n"
    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades |\n"
    md += "|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['profit_factor']:.2f} | {r['trades']} |\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("Leaderboard generated: LEADERBOARD.md")

if __name__ == "__main__":
    run_leaderboard()
