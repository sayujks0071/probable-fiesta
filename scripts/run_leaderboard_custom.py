#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(repo_root)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LeaderboardCustom")

# --- MOCK API CLIENT ---
class MockAPIClient:
    def __init__(self, api_key=None, host=None):
        self.api_key = api_key
        self.host = host
        logger.info("Initialized MockAPIClient for Backtesting")

    def history(self, symbol, exchange="NSE", interval="15m", start_date=None, end_date=None, max_retries=3):
        """Generate Synthetic Data based on symbol to simulate regimes."""
        # logger.info(f"Generating synthetic data for {symbol}...")

        # Parse dates
        if not start_date: start_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
        if not end_date: end_date = datetime.now().strftime("%Y-%m-%d")

        dates = pd.date_range(start=start_date, end=end_date, freq='15min') # 15 min intervals
        n = len(dates)

        # Base price
        price = 1000.0
        if "NIFTY" in symbol: price = 20000.0
        elif "SILVER" in symbol: price = 70000.0

        # Generate Regimes
        # 1. Trend Up (First 30%)
        # 2. Chop/Range (Middle 40%)
        # 3. Trend Down/Volatile (Last 30%)

        n_trend = int(n * 0.3)
        n_chop = int(n * 0.4)
        n_down = n - n_trend - n_chop

        # Random Walk with Drift
        np.random.seed(42) # Reproducible

        # Trend Up
        returns_trend = np.random.normal(0.0001, 0.002, n_trend) # Positive drift
        price_trend = price * np.exp(np.cumsum(returns_trend))

        # Chop
        last_price = price_trend[-1]
        returns_chop = np.random.normal(0.0, 0.001, n_chop) # No drift, lower vol
        price_chop = last_price * np.exp(np.cumsum(returns_chop))

        # Down/Volatile
        last_price = price_chop[-1]
        returns_down = np.random.normal(-0.0001, 0.003, n_down) # Negative drift, high vol
        price_down = last_price * np.exp(np.cumsum(returns_down))

        prices = np.concatenate([price_trend, price_chop, price_down])

        # Create OHLC
        # Open is close of prev (approx)
        opens = prices # Simplify
        highs = prices * (1 + np.abs(np.random.normal(0, 0.002, n)))
        lows = prices * (1 - np.abs(np.random.normal(0, 0.002, n)))
        closes = prices + np.random.normal(0, 0.001, n)
        volumes = np.random.randint(1000, 50000, n)

        df = pd.DataFrame({
            'datetime': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })

        # Fix highs/lows to encase open/close
        df['high'] = df[['open', 'close', 'high']].max(axis=1)
        df['low'] = df[['open', 'close', 'low']].min(axis=1)

        df = df.set_index('datetime')
        return df

    def get_quote(self, symbol, exchange="NSE"):
        return {'ltp': 1000.0}

    def placesmartorder(self, **kwargs):
        return {'status': 'success', 'order_id': 'mock_123'}

# Monkey Patch
try:
    from openalgo.strategies.utils import simple_backtest_engine
    simple_backtest_engine.APIClient = MockAPIClient
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    import simple_backtest_engine
    simple_backtest_engine.APIClient = MockAPIClient
    from simple_backtest_engine import SimpleBacktestEngine

# --- STRATEGIES CONFIG ---
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
        "exchange": "MCX"
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
        "vol_multiplier": [1.0],
        "use_poc_filter": [False],
        "use_trend_filter": [False]
    },
    "MCX_Momentum": {
        "adx_threshold": [30],
        "sma_period": [50],
        "min_atr": [10]
    },
    "AI_Hybrid": {
        "rsi_lower": [30],
        "rsi_upper": [60],
    },
    "ML_Momentum": {
        "threshold": [0.01],
        "vol_multiplier": [0.5],
        "sma_period": [200]
    }
}

def load_strategy_module(filepath):
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

def run_single_backtest(engine, module, strat_config, params, run_name):
    # Wrapper
    original_gen = module.generate_signal

    # Check if module expects params
    import inspect
    sig = inspect.signature(original_gen)
    has_params = 'params' in sig.parameters

    def wrapped_gen(df, client=None, symbol=None):
        if has_params:
            return original_gen(df, client, symbol, params=params)
        else:
            return original_gen(df, client, symbol)

    class ModuleWrapper:
        pass
    wrapper = ModuleWrapper()
    wrapper.generate_signal = wrapped_gen

    # Copy attributes
    for attr in ['ATR_SL_MULTIPLIER', 'ATR_TP_MULTIPLIER', 'TIME_STOP_BARS', 'BREAKEVEN_TRIGGER_R']:
        if hasattr(module, attr):
            setattr(wrapper, attr, getattr(module, attr))

    # Defaults
    if not hasattr(wrapper, 'TIME_STOP_BARS'): wrapper.TIME_STOP_BARS = 32 # 8 hours (15m)

    start_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    res = engine.run_backtest(
        strategy_module=wrapper,
        symbol=strat_config['symbol'],
        exchange=strat_config['exchange'],
        start_date=start_date,
        end_date=end_date,
        interval="15m"
    )

    metrics = res.get('metrics', {})
    return {
        "strategy": run_name,
        "base_strategy": strat_config['name'],
        "params": params,
        "total_return": metrics.get('total_return_pct', 0),
        "sharpe": metrics.get('sharpe_ratio', 0),
        "drawdown": metrics.get('max_drawdown_pct', 0),
        "win_rate": metrics.get('win_rate', 0),
        "trades": res.get('total_trades', 0),
        "profit_factor": metrics.get('profit_factor', 0)
    }

def main():
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    results = []

    logger.info("Running Optimization Grid...")
    for strat_config in STRATEGIES:
        if strat_config['name'] not in TUNING_CONFIG: continue
        import itertools
        grid = TUNING_CONFIG[strat_config['name']]
        keys = list(grid.keys())
        values = list(grid.values())
        combinations = list(itertools.product(*values))

        module = load_strategy_module(strat_config['file'])
        if not module: continue

        for i, combo in enumerate(combinations):
            params = dict(zip(keys, combo))
            variant_name = f"{strat_config['name']}_v{i+1}"
            logger.info(f"Running {variant_name} with {params}")
            res = run_single_backtest(engine, module, strat_config, params, variant_name)
            results.append(res)

    # Sort & Display
    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    print("\n" + "="*120)
    print(f"{'Rank':<5} {'Strategy':<20} {'Sharpe':<8} {'Return %':<10} {'DD %':<8} {'Win Rate':<10} {'Trades':<8} {'Params'}")
    print("-" * 120)
    for i, r in enumerate(results):
        p_str = str(r['params'])
        if len(p_str) > 40: p_str = p_str[:37] + "..."
        print(f"{i+1:<5} {r['strategy']:<20} {r['sharpe']:<8.2f} {r['total_return']:<10.2f} {r['drawdown']:<8.2f} {r['win_rate']:<10.2f} {r['trades']:<8} {p_str}")
    print("="*120 + "\n")

    # Save to JSON
    with open("leaderboard_custom.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
