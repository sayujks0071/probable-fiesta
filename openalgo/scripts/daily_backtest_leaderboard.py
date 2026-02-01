#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
import importlib.util
import argparse

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
        "symbol": "SILVERMIC", # Will try to resolve if needed
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
        "threshold": [150, 160]
    },
    "MCX_Momentum": {
        "adx_threshold": [20, 30],
        "period_rsi": [10, 14]
    },
    "AI_Hybrid": {
        "rsi_lower": [25, 35],
        "rsi_upper": [60, 70]
    },
    "ML_Momentum": {
        "threshold": [0.01, 0.02]
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
        if not os.path.exists(os.path.join(repo_root, filepath)):
             logger.warning(f"Strategy file not found: {filepath}")
             return None

        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def calculate_extended_metrics(res):
    metrics = res.get('metrics', {})
    trades = res.get('closed_trades', [])

    # Expectancy
    win_rate = metrics.get('win_rate', 0) / 100.0
    avg_win = metrics.get('avg_win', 0)
    avg_loss = metrics.get('avg_loss', 0) # usually negative
    expectancy = (avg_win * win_rate) + (avg_loss * (1 - win_rate))

    # Time in Market
    total_duration = timedelta(0)
    for t in trades:
        if t.get('exit_time') and t.get('entry_time'):
            try:
                start = pd.to_datetime(t['entry_time'])
                end = pd.to_datetime(t['exit_time'])
                total_duration += (end - start)
            except:
                pass

    # Format duration
    total_hours = total_duration.total_seconds() / 3600.0

    return expectancy, total_hours

def run_leaderboard(output_dir=None):
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = os.getcwd()

    engine = SimpleBacktestEngine(initial_capital=100000.0)

    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
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
            runs.extend(variants)

        for run in runs:
            logger.info(f"  > Variant: {run['name']} Params: {run['params']}")

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
                # Copy attributes if they exist
                for attr in ['ATR_SL_MULTIPLIER', 'ATR_TP_MULTIPLIER', 'TIME_STOP_BARS', 'BREAKEVEN_TRIGGER_R']:
                    if hasattr(module, attr):
                        setattr(wrapper, attr, getattr(module, attr))

                # Defaults if not present
                if not hasattr(wrapper, 'ATR_SL_MULTIPLIER'): wrapper.ATR_SL_MULTIPLIER = 1.5
                if not hasattr(wrapper, 'ATR_TP_MULTIPLIER'): wrapper.ATR_TP_MULTIPLIER = 2.5

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
                expectancy, time_in_market = calculate_extended_metrics(res)

                results.append({
                    "strategy": run['name'],
                    "params": run['params'],
                    "total_return": metrics.get('total_return_pct', 0),
                    "sharpe": metrics.get('sharpe_ratio', 0),
                    "drawdown": metrics.get('max_drawdown_pct', 0),
                    "win_rate": metrics.get('win_rate', 0),
                    "trades": res.get('total_trades', 0),
                    "profit_factor": metrics.get('profit_factor', 0),
                    "expectancy": expectancy,
                    "time_in_market_hrs": time_in_market
                })

            except Exception as e:
                logger.error(f"Error backtesting {run['name']}: {e}", exc_info=True)

    # Sort by Sharpe Ratio (Primary) then Return
    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    # Save JSON
    json_path = os.path.join(output_dir, "leaderboard.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=4)

    # Generate Markdown
    md = "# Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades | Expectancy | Exposure (Hrs) |\n"
    md += "|---|---|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['profit_factor']:.2f} | {r['trades']} | {r['expectancy']:.2f} | {r['time_in_market_hrs']:.1f} |\n"

    md_path = os.path.join(output_dir, "LEADERBOARD.md")
    with open(md_path, "w") as f:
        f.write(md)

    logger.info(f"Leaderboard generated: {md_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Backtest Leaderboard")
    parser.add_argument("--output", type=str, default=".", help="Output directory")
    args = parser.parse_args()

    run_leaderboard(args.output)
