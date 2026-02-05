#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
import importlib.util

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import LocalBacktestEngine
try:
    from openalgo.strategies.utils.local_backtest_engine import LocalBacktestEngine
except ImportError:
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from local_backtest_engine import LocalBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

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
        "symbol": "SILVER", # Mapped to SI=F in engine
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
    },
    {
        "name": "SuperTrend_VWAP_v2",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy_v2.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "AI_Hybrid_v2",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout_v2.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "ML_Momentum_v2",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy_v2.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    }
]

TUNING_CONFIG = {
    "ML_Momentum_v2": {
        "threshold": [0.005, 0.003],
        "vol_multiplier": [0.5, 0.3]
    },
    "AI_Hybrid_v2": {
        "rsi_lower": [20, 25],
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
    # Use Local Engine
    engine = LocalBacktestEngine(initial_capital=100000.0)

    # Default to recent data (last 59 days for 15m), but allow env var override
    default_start = (datetime.now() - timedelta(days=59)).strftime("%Y-%m-%d")
    default_end = datetime.now().strftime("%Y-%m-%d")

    start_date = os.getenv("BACKTEST_START", default_start)
    end_date = os.getenv("BACKTEST_END", default_end)
    interval = os.getenv("BACKTEST_INTERVAL", "15m")

    results = []

    for strat_config in STRATEGIES:
        logger.info(f"Backtesting {strat_config['name']}...")

        module = load_strategy_module(strat_config['file'])
        if not module:
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"Strategy {strat_config['name']} does not have 'generate_signal'. Skipping.")
            continue

        runs = [{"name": strat_config['name'], "params": None}]

        if strat_config['name'] in TUNING_CONFIG:
            variants = generate_variants(strat_config['name'], TUNING_CONFIG[strat_config['name']])
            runs.extend(variants)

        for run in runs:
            logger.info(f"  > Variant: {run['name']} Params: {run['params']}")

            original_gen = module.generate_signal

            params = run['params']
            if params:
                def wrapped_gen(df, client=None, symbol=None):
                    return original_gen(df, client, symbol, params=params)

                class ModuleWrapper:
                    pass
                wrapper = ModuleWrapper()
                wrapper.generate_signal = wrapped_gen
                # Copy attributes used by engine
                wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
                wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)
                wrapper.TIME_STOP_BARS = getattr(module, 'TIME_STOP_BARS', 12)
                wrapper.BREAKEVEN_TRIGGER_R = getattr(module, 'BREAKEVEN_TRIGGER_R', 1.5)

                target_module = wrapper
            else:
                target_module = module

            try:
                res = engine.run_backtest(
                    strategy_module=target_module,
                    symbol=strat_config['symbol'],
                    exchange=strat_config['exchange'],
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval
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

    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    with open("leaderboard.json", "w") as f:
        json.dump(results, f, indent=4)

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
    run_leaderboard()
