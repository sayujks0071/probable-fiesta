#!/usr/bin/env python3
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util
import logging
from typing import Dict, List, Any

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(repo_root)

# Import Backtest Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyntheticBacktest")

# --- Synthetic Data Generation ---
def generate_trend_data(n_bars=1000, start_price=100.0, trend_strength=0.0005, noise_std=0.2):
    """Generates trending market data."""
    dates = [datetime.now() - timedelta(minutes=15 * (n_bars - i)) for i in range(n_bars)]
    prices = [start_price]
    for _ in range(1, n_bars):
        change = np.random.normal(0, noise_std) + trend_strength * prices[-1]
        prices.append(prices[-1] + change)

    df = pd.DataFrame({'close': prices, 'datetime': dates})
    df['open'] = df['close'] + np.random.normal(0, noise_std/2, n_bars)
    df['high'] = df[['open', 'close']].max(axis=1) + abs(np.random.normal(0, noise_std/2, n_bars))
    df['low'] = df[['open', 'close']].min(axis=1) - abs(np.random.normal(0, noise_std/2, n_bars))
    df['volume'] = np.random.randint(100, 1000, n_bars)

    df = df.set_index('datetime')
    return df

def generate_range_data(n_bars=1000, base_price=100.0, amplitude=5.0, period=100, noise_std=0.2):
    """Generates ranging market data (sine wave)."""
    dates = [datetime.now() - timedelta(minutes=15 * (n_bars - i)) for i in range(n_bars)]
    x = np.linspace(0, 4 * np.pi, n_bars)
    prices = base_price + amplitude * np.sin(x) + np.random.normal(0, noise_std, n_bars)

    df = pd.DataFrame({'close': prices, 'datetime': dates})
    df['open'] = df['close'] + np.random.normal(0, noise_std/2, n_bars)
    df['high'] = df[['open', 'close']].max(axis=1) + abs(np.random.normal(0, noise_std/2, n_bars))
    df['low'] = df[['open', 'close']].min(axis=1) - abs(np.random.normal(0, noise_std/2, n_bars))
    df['volume'] = np.random.randint(100, 1000, n_bars)

    df = df.set_index('datetime')
    return df

# --- Strategies Config ---
STRATEGIES = [
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "params_grid": {
            "threshold": [0.01, 0.02],
            "vol_multiplier": [0.5, 1.0]
        }
    },
    {
        "name": "AI_Hybrid",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "params_grid": {
            "rsi_lower": [30, 35],
            "rsi_upper": [60, 65]
        }
    },
    {
        "name": "MCX_Momentum",
        "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
        "params_grid": {
            "adx_threshold": [20, 25],
            "period_rsi": [14]
        }
    },
    # {
    #     "name": "SuperTrend_VWAP",
    #     "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
    #     "params_grid": {
    #         "threshold": [150],
    #         "adx_threshold": [20, 25]
    #     }
    # }
]

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

def run_tuning():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    # Generate Datasets
    trend_df = generate_trend_data(n_bars=400, trend_strength=0.001)
    range_df = generate_range_data(n_bars=400)

    datasets = {
        "TREND": trend_df,
        "RANGE": range_df
    }

    results = []

    import itertools

    for strat_config in STRATEGIES:
        module = load_strategy_module(strat_config['file'])
        if not module: continue

        # Generate Parameter Combinations
        keys = list(strat_config['params_grid'].keys())
        values = list(strat_config['params_grid'].values())
        combinations = list(itertools.product(*values))

        for combo in combinations:
            params = dict(zip(keys, combo))
            variant_name = f"{strat_config['name']}_{combo}"

            # Monkey Patch or Wrapper for Params
            original_gen = module.generate_signal

            # Wrapper to inject params
            def make_wrapper(p):
                def wrapped_gen(df, client=None, symbol=None):
                    return original_gen(df, client, symbol, params=p)
                return wrapped_gen

            # Create a mock module object
            class ModuleWrapper:
                pass

            wrapper = ModuleWrapper()
            wrapper.generate_signal = make_wrapper(params)

            # Copy other attributes if needed (Time Stop, etc)
            if hasattr(module, 'TIME_STOP_BARS'): wrapper.TIME_STOP_BARS = module.TIME_STOP_BARS
            if hasattr(module, 'ATR_SL_MULTIPLIER'): wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
            if hasattr(module, 'ATR_TP_MULTIPLIER'): wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)

            for regime, df in datasets.items():
                try:
                    print(f"Running {variant_name} on {regime}...")
                    res = engine.run_backtest(
                        strategy_module=wrapper,
                        symbol="SYNTH",
                        exchange="TEST",
                        start_date="2024-01-01",
                        end_date="2024-02-01",
                        df=df
                    )

                    metrics = res.get('metrics', {})
                    results.append({
                        "strategy": strat_config['name'],
                        "variant": str(params),
                        "regime": regime,
                        "sharpe": metrics.get('sharpe_ratio', 0),
                        "return": metrics.get('total_return_pct', 0),
                        "trades": res.get('total_trades', 0),
                        "dd": metrics.get('max_drawdown_pct', 0)
                    })
                except Exception as e:
                    logger.error(f"Error running {variant_name} on {regime}: {e}")

    # Process Results
    df_res = pd.DataFrame(results)
    if df_res.empty:
        print("No results generated.")
        return

    print("\n--- Leaderboard by Regime ---")
    for regime in ["TREND", "RANGE"]:
        print(f"\nREGIME: {regime}")
        subset = df_res[df_res['regime'] == regime].sort_values('sharpe', ascending=False).head(5)
        print(subset[['strategy', 'variant', 'sharpe', 'return', 'trades', 'dd']].to_string(index=False))

    # Calculate Stability (Average Sharpe across regimes)
    stability = df_res.groupby(['strategy', 'variant'])['sharpe'].mean().reset_index()
    stability = stability.sort_values('sharpe', ascending=False)

    print("\n--- Overall Stable Strategies (Avg Sharpe) ---")
    print(stability.head(10).to_string(index=False))

    # Save detailed
    df_res.to_csv("backtest_results_detailed.csv", index=False)

if __name__ == "__main__":
    run_tuning()
