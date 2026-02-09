#!/usr/bin/env python3
"""
Backtest Leaderboard & Analysis Script V2
Runs backtests using yfinance data (Last 60 days).
Includes Parameter Tuning for V2 Strategies.
"""
import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util
import yfinance as yf
import itertools

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import OpenAlgo modules
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AnalysisLeaderboard")

# Configuration
# yfinance 15m data limit is 60 days
START_DATE = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d")
END_DATE = datetime.now().strftime("%Y-%m-%d")
INITIAL_CAPITAL = 100000.0

STRATEGIES = [
    # Originals
    {
        "name": "SuperTrend_VWAP",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    },
    {
        "name": "AI_Hybrid",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    },
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    },
    # Improved V2
    {
        "name": "SuperTrend_VWAP_v2",
        "file": "openalgo/strategies/scripts/supertrend_vwap_v2.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    },
    {
        "name": "AI_Hybrid_v2",
        "file": "openalgo/strategies/scripts/ai_hybrid_v2.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    },
    {
        "name": "ML_Momentum_v2",
        "file": "openalgo/strategies/scripts/ml_momentum_v2.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    }
]

TUNING_CONFIG = {
    "SuperTrend_VWAP_v2": {
        "stop_pct": [1.5, 2.0],
        "threshold": [140, 160]
    },
    "AI_Hybrid_v2": {
        "rsi_lower": [25, 30],
        "rsi_upper": [60, 70]
    },
    "ML_Momentum_v2": {
        "threshold": [0.01, 0.02]
    }
}

class MockAPIClientAdapter:
    """Adapts APIClient interface to yfinance"""
    def __init__(self):
        self.symbol_map = {
            "NIFTY": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "INDIA VIX": "^INDIAVIX",
            "NIFTY 50": "^NSEI",
            "NIFTY BANK": "^NSEBANK",
            "RELIANCE": "RELIANCE.NS"
        }

    def history(self, symbol, exchange="NSE", interval="5m", start_date=None, end_date=None, max_retries=3):
        yf_symbol = self.symbol_map.get(symbol.upper(), symbol)

        # Convert interval to yfinance format
        yf_interval = interval
        if interval == "5m": yf_interval = "5m"
        elif interval == "15m": yf_interval = "15m"
        elif interval == "1h": yf_interval = "1h"
        elif interval == "1d": yf_interval = "1d"

        try:
            # Check if start_date is within limit for intraday
            if interval.endswith('m') or interval.endswith('h'):
                # Max 60 days
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                limit_dt = datetime.now() - timedelta(days=59)
                if start_dt < limit_dt:
                    start_date = limit_dt.strftime("%Y-%m-%d")

            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=yf_interval, progress=False)

            if df.empty:
                return pd.DataFrame()

            # Normalize columns
            if isinstance(df.columns, pd.MultiIndex):
                # Flatten MultiIndex (e.g. ('Close', 'AAPL') -> 'Close')
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()
            df.columns = [str(c).lower() for c in df.columns]

            # Rename
            rename_map = {
                'date': 'datetime',
                'datetime': 'datetime',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                'adj close': 'adj_close'
            }
            df = df.rename(columns=rename_map)

            if 'datetime' not in df.columns and 'date' in df.columns:
                 df['datetime'] = pd.to_datetime(df['date'])

            if 'datetime' in df.columns:
                df = df.set_index('datetime')

            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            return df
        except Exception as e:
            return pd.DataFrame()

    def placesmartorder(self, strategy, symbol, action, exchange, price_type, product, quantity, position_size):
        logger.info(f"[MOCK ORDER] {action} {quantity} {symbol} @ {price_type}")
        return {"status": "success", "message": "Order placed via Mock"}

    def get_quote(self, symbol, exchange="NSE", max_retries=3):
        return {'ltp': 0.0}

    def get_option_chain(self, symbol, exchange="NFO", max_retries=3):
        return {}

    def get_vix(self):
        df = self.history("INDIA VIX", "NSE", "1d", START_DATE, END_DATE)
        if not df.empty:
            return df.iloc[-1]['close']
        return 15.0

class MockedBacktestEngine(SimpleBacktestEngine):
    """Backtest Engine using Mock API Client"""
    def __init__(self, initial_capital=100000.0):
        super().__init__(initial_capital=initial_capital)
        self.client = MockAPIClientAdapter()
        # logger.info("Initialized MockedBacktestEngine with MockAPIClientAdapter")

def load_strategy_module(filepath):
    """Load a strategy script as a module."""
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def generate_variants(base_name, grid):
    keys = list(grid.keys())
    values = list(grid.values())
    combinations = list(itertools.product(*values))

    variants = []
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        variants.append({
            "name": f"{base_name}_v{i+1}",
            "params": params,
            "is_variant": True
        })
    return variants

def run_analysis():
    engine = MockedBacktestEngine(initial_capital=INITIAL_CAPITAL)
    results = []

    logger.info(f"Running Analysis from {START_DATE} to {END_DATE}")

    for strat_config in STRATEGIES:
        module = load_strategy_module(strat_config['file'])
        if not module: continue

        if not hasattr(module, 'generate_signal'): continue

        runs = [{"name": strat_config['name'], "params": None}]

        if strat_config['name'] in TUNING_CONFIG:
            variants = generate_variants(strat_config['name'], TUNING_CONFIG[strat_config['name']])
            runs.extend(variants)

        for run in runs:
            logger.info(f"Testing {run['name']} Params: {run['params']}")
            try:
                # Set default ATR params
                if hasattr(module, 'ATR_SL_MULTIPLIER'):
                    module.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)

                # We need to pass params to generate_signal wrapper if variant
                # We can do this by wrapping the module

                original_gen = module.generate_signal
                params = run['params']

                # Create a wrapper function that injects params
                def wrapped_gen(df, client=None, symbol=None):
                    # For original strategies (non-v2), they might accept params if I updated them
                    # Or they accept kwargs
                    try:
                        return original_gen(df, client, symbol, params=params)
                    except TypeError:
                        # Fallback for old signature
                        return original_gen(df, client, symbol)

                # Create a temporary object acting as module
                class ModuleWrapper:
                    pass
                wrapper = ModuleWrapper()
                wrapper.generate_signal = wrapped_gen
                # Copy attributes needed by engine
                for attr in ['ATR_SL_MULTIPLIER', 'ATR_TP_MULTIPLIER', 'TIME_STOP_BARS', 'BREAKEVEN_TRIGGER_R', 'check_exit']:
                    if hasattr(module, attr):
                        setattr(wrapper, attr, getattr(module, attr))

                res = engine.run_backtest(
                    strategy_module=wrapper,
                    symbol=strat_config['symbol'],
                    exchange=strat_config['exchange'],
                    start_date=START_DATE,
                    end_date=END_DATE,
                    interval="15m"
                )

                if 'error' in res:
                    results.append({"strategy": run['name'], "error": res['error']})
                    continue

                metrics = res.get('metrics', {})
                results.append({
                    "strategy": run['name'],
                    "params": run['params'],
                    "sharpe": metrics.get('sharpe_ratio', 0),
                    "total_return": metrics.get('total_return_pct', 0),
                    "drawdown": metrics.get('max_drawdown_pct', 0),
                    "trades": res.get('total_trades', 0),
                    "win_rate": metrics.get('win_rate', 0),
                    "profit_factor": metrics.get('profit_factor', 0)
                })

            except Exception as e:
                logger.error(f"Error executing {run['name']}: {e}", exc_info=True)
                results.append({"strategy": run['name'], "error": str(e)})

    # Sort results
    valid_results = [r for r in results if 'error' not in r]
    error_results = [r for r in results if 'error' in r]

    valid_results.sort(key=lambda x: (x.get('sharpe', 0), x.get('total_return', 0)), reverse=True)

    final_results = valid_results + error_results

    # Output JSON
    with open("leaderboard.json", "w") as f:
        json.dump(final_results, f, indent=4)

    # Print Summary
    print("\n" + "="*80)
    print("BACKTEST LEADERBOARD (yfinance Data: Last 50 Days)")
    print("="*80)
    print(f"{'Rank':<5} {'Strategy':<25} {'Sharpe':<8} {'Return %':<10} {'DD %':<8} {'Win Rate':<10} {'Trades':<8}")
    print("-" * 80)

    for i, r in enumerate(valid_results):
        name = r['strategy']
        print(f"{i+1:<5} {name:<25} {r['sharpe']:<8.2f} {r['total_return']:<10.2f} {r['drawdown']:<8.2f} {r['win_rate']:<10.2f} {r['trades']:<8}")

    if error_results:
        print("\nFailed Strategies:")
        for r in error_results:
            print(f"- {r['strategy']}: {r['error']}")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_analysis()
