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
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import Backtest Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

# Mock API Client to avoid connection refused errors during backtest
class MockAPIClient:
    def __init__(self, api_key=None, host=None):
        self.host = host
        self.api_key = api_key

    def history(self, symbol, exchange=None, interval="15m", start_date=None, end_date=None):
        # Return VIX data fast
        if "VIX" in str(symbol).upper():
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            dates = pd.date_range(start=start, end=end, freq="D")
            df = pd.DataFrame(index=dates)
            df['close'] = 15.0
            return df

        # Return synthetic data for others
        return generate_synthetic_data(symbol, start_date, end_date, interval)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

STRATEGIES = [
    {
        "name": "SuperTrend_VWAP",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "symbol": "NIFTY", # Default test symbol
        "exchange": "NSE_INDEX"
    },
    {
        "name": "MCX_Momentum",
        "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
        "symbol": "SILVERMIC", # Will try to resolve if needed, but engine needs raw symbol usually?
                               # Engine loads data. We can use a proxy symbol like 'SILVER' if using mock data,
                               # but usually specific symbol needed.
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

TUNING_CONFIG = {
    "SuperTrend_VWAP": {
        "stop_pct": [1.5, 2.0],
        "adx_threshold": [15, 20]
    },
    "MCX_Momentum": {
        "adx_threshold": [20, 25],
        "period_rsi": [14]
    },
    "AI_Hybrid": {
        "rsi_lower": [30, 35],
        "rsi_upper": [60, 65]
    },
    "ML_Momentum": {
        "threshold": [0.01, 0.02]
    }
}

def generate_synthetic_data(symbol, start_date, end_date, interval="15m"):
    # Generate dates
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    # Map 15m to 15min for pandas
    freq = interval.replace('m', 'min') if interval.endswith('m') else interval
    dates = pd.date_range(start=start, end=end, freq=freq)

    n = len(dates)
    if n == 0: return pd.DataFrame()

    # Random walk
    np.random.seed(42)
    returns = np.random.normal(0, 0.002, n)

    # Add Regimes
    trend = np.zeros(n)
    trend[:n//3] = 0.0005 # Up
    trend[n//3:2*n//3] = 0.0 # Flat
    trend[2*n//3:] = -0.0005 # Down

    returns += trend

    price = 10000 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(index=dates)
    df['close'] = price
    df['open'] = price * (1 + np.random.normal(0, 0.001, n))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.002, n)))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.002, n)))
    df['volume'] = np.random.randint(1000, 10000, n)

    return df

def generate_variants(base_name, grid):
    import itertools
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

def run_leaderboard(mock=False):
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    if mock:
        # Force mock client on engine instance
        engine.client = MockAPIClient()

        # Monkey Patch load_historical_data
        original_load = engine.load_historical_data
        def mock_load(symbol, exchange, start_date, end_date, interval="15m"):
            logger.info(f"Mocking data for {symbol}")
            return generate_synthetic_data(symbol, start_date, end_date, interval)
        engine.load_historical_data = mock_load

        # Monkey Patch APIClient in the module where SimpleBacktestEngine is defined
        import sys
        # Patch SimpleBacktestEngine's reference
        if 'openalgo.strategies.utils.simple_backtest_engine' in sys.modules:
            sys.modules['openalgo.strategies.utils.simple_backtest_engine'].APIClient = MockAPIClient
        elif 'simple_backtest_engine' in sys.modules:
            sys.modules['simple_backtest_engine'].APIClient = MockAPIClient

        # Patch trading_utils reference (used by strategies)
        # Try to import it first to ensure it's in sys.modules
        try:
            import openalgo.strategies.utils.trading_utils as tu
            tu.APIClient = MockAPIClient
        except ImportError:
            pass

        try:
            import trading_utils as tu_local
            tu_local.APIClient = MockAPIClient
        except ImportError:
            pass

        # Patch in sys.modules directly if present
        for module_name in list(sys.modules.keys()):
            if 'trading_utils' in module_name:
                try:
                    sys.modules[module_name].APIClient = MockAPIClient
                except AttributeError:
                    pass

    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d") # Increased to 5 days
    end_date = datetime.now().strftime("%Y-%m-%d")

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
        runs = [{"name": strat_config['name'], "params": None}]

        if strat_config['name'] in TUNING_CONFIG:
            variants = generate_variants(strat_config['name'], TUNING_CONFIG[strat_config['name']])
            # Limit to top 3 variants if too many? For now run all (small grid)
            runs.extend(variants)

        for run in runs:
            logger.info(f"  > Variant: {run['name']} Params: {run['params']}")

            # Monkey patch module to accept params if needed, or pass via run_backtest extension?
            # SimpleBacktestEngine.run_backtest calls module.generate_signal(..., symbol=symbol)
            # It doesn't pass 'params'.
            # We need to wrap the module or monkey patch generate_signal.

            original_gen = module.generate_signal

            # Create a partial/wrapper
            params = run['params']
            if params:
                def wrapped_gen(df, client=None, symbol=None):
                    return original_gen(df, client, symbol, params=params)

                # Create a temporary object acting as module
                class ModuleWrapper:
                    pass
                wrapper = ModuleWrapper()
                wrapper.generate_signal = wrapped_gen
                wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
                wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)
                target_module = wrapper
            else:
                target_module = module

            try:
                # Run Backtest
                res = engine.run_backtest(
                    strategy_module=target_module,
                    symbol=strat_config['symbol'],
                    exchange=strat_config['exchange'],
                    start_date=start_date,
                    end_date=end_date,
                    interval="15m"
                )

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
                    "profit_factor": metrics.get('profit_factor', 0)
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
    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades |\n"
    md += "|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['profit_factor']:.2f} | {r['trades']} |\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("Leaderboard generated: LEADERBOARD.md")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Run with mock data")
    args = parser.parse_args()
    run_leaderboard(mock=args.mock)
