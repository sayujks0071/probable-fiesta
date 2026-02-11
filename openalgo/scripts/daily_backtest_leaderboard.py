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
    from openalgo.strategies.utils.synthetic_data import generate_trend_data, generate_range_data
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine
    from synthetic_data import generate_trend_data, generate_range_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

STRATEGIES = [
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
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
    }
]

# Tuned Parameter Grids (Small for demo speed)
TUNING_CONFIG = {
    "ML_Momentum": {
        "threshold": [0.01, 0.015],
        "atr_period": [14, 20],
        "use_filters": [False] # Disable external filters for synthetic data
    },
    "MCX_Momentum": {
        "adx_threshold": [20, 25],
        "trend_filter_sma": [0, 50],
        "min_atr": [0] # Disable min atr for synthetic as it might vary
    },
    "AI_Hybrid": {
        "adx_threshold": [20, 30],
        "rsi_lower": [30, 35],
        "rsi_upper": [65, 70]
    }
}

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

def run_leaderboard():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    # Generate Synthetic Data
    logger.info("Generating Synthetic Data...")
    trend_df = generate_trend_data(n_bars=500, start_price=1000, volatility=0.005, trend_slope=0.0003)
    range_df = generate_range_data(n_bars=500, start_price=1000, volatility=0.005, amplitude=20.0)

    regimes = {
        "TREND": trend_df,
        "RANGE": range_df
    }

    all_results = []

    for regime_name, df in regimes.items():
        logger.info(f"--- Processing Regime: {regime_name} ---")

        for strat_config in STRATEGIES:
            module = load_strategy_module(strat_config['file'])
            if not module: continue
            if not hasattr(module, 'generate_signal'):
                logger.warning(f"Strategy {strat_config['name']} missing generate_signal")
                continue

            # Determine variants to run
            # Base run (default params)
            runs = [{"name": strat_config['name'], "params": None}]

            if strat_config['name'] in TUNING_CONFIG:
                variants = generate_variants(strat_config['name'], TUNING_CONFIG[strat_config['name']])
                runs.extend(variants)

            for run in runs:
                original_gen = module.generate_signal

                # Create wrapper for params
                params = run['params']
                if params:
                    def wrapped_gen(df, client=None, symbol=None):
                        return original_gen(df, client, symbol, params=params)

                    class ModuleWrapper: pass
                    wrapper = ModuleWrapper()
                    wrapper.generate_signal = wrapped_gen
                    # Inject module level attributes if needed
                    if hasattr(module, 'TIME_STOP_BARS'):
                        wrapper.TIME_STOP_BARS = module.TIME_STOP_BARS
                    if hasattr(module, 'ATR_SL_MULTIPLIER'):
                        wrapper.ATR_SL_MULTIPLIER = module.ATR_SL_MULTIPLIER

                    target_module = wrapper
                else:
                    target_module = module

                try:
                    # Run Backtest with synthetic DF
                    res = engine.run_backtest(
                        strategy_module=target_module,
                        symbol="SYNTH",
                        exchange="MOCK",
                        start_date="2024-01-01", # Dummy
                        end_date="2024-02-01",   # Dummy
                        interval="15m",
                        df=df
                    )

                    metrics = res.get('metrics', {})
                    all_results.append({
                        "regime": regime_name,
                        "strategy": run['name'],
                        "params": run['params'],
                        "sharpe": metrics.get('sharpe_ratio', 0),
                        "return_pct": metrics.get('total_return_pct', 0),
                        "drawdown": metrics.get('max_drawdown_pct', 0),
                        "trades": res.get('total_trades', 0),
                        "win_rate": metrics.get('win_rate', 0)
                    })
                except Exception as e:
                    logger.error(f"Error backtesting {run['name']}: {e}", exc_info=True)

    # Generate Markdown Report
    md = "# Backtest Leaderboard (Synthetic Regimes)\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"

    # Per Regime Tables
    for regime in ["TREND", "RANGE"]:
        md += f"## Regime: {regime}\n\n"
        md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Trades | Win Rate % |\n"
        md += "|---|---|---|---|---|---|---|\n"

        subset = [r for r in all_results if r['regime'] == regime]
        subset.sort(key=lambda x: (x['sharpe'], x['return_pct']), reverse=True)

        for i, r in enumerate(subset):
            md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['return_pct']:.2f}% | {r['drawdown']:.2f}% | {r['trades']} | {r['win_rate']:.2f}% |\n"
        md += "\n"

    # Overall Ranking (Average Sharpe)
    md += "## Overall Ranking (Average Sharpe)\n\n"
    md += "| Rank | Strategy | Avg Sharpe |\n"
    md += "|---|---|---|\n"

    strategy_sharpes = {}
    for r in all_results:
        if r['strategy'] not in strategy_sharpes:
            strategy_sharpes[r['strategy']] = []
        strategy_sharpes[r['strategy']].append(r['sharpe'])

    avg_sharpes = []
    for strat, sharpes in strategy_sharpes.items():
        avg_sharpes.append({"strategy": strat, "avg_sharpe": sum(sharpes)/len(sharpes)})

    avg_sharpes.sort(key=lambda x: x['avg_sharpe'], reverse=True)

    for i, r in enumerate(avg_sharpes):
        md += f"| {i+1} | {r['strategy']} | {r['avg_sharpe']:.2f} |\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("Leaderboard generated: LEADERBOARD.md")

if __name__ == "__main__":
    run_leaderboard()
