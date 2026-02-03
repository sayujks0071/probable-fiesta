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
        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def monte_carlo_simulation(trades_pnl_pct, num_simulations=1000):
    """
    Run Monte Carlo Simulation on trade returns to estimate risk.
    Returns: Avg Return, 95% VaR (Max Drawdown at 95th percentile)
    """
    if not trades_pnl_pct or len(trades_pnl_pct) < 5:
        return 0.0, 0.0

    returns = np.array(trades_pnl_pct) / 100.0 # Convert to decimal

    sim_returns = []
    sim_max_dds = []

    for _ in range(num_simulations):
        # Bootstrap resampling
        sample = np.random.choice(returns, size=len(returns), replace=True)
        # Calculate equity curve (starting at 1.0)
        cum_returns = np.cumprod(1 + sample)
        final_ret = cum_returns[-1] - 1

        # Max Drawdown
        peak = np.maximum.accumulate(cum_returns)
        drawdown = (peak - cum_returns) / peak
        max_dd = np.max(drawdown)

        sim_returns.append(final_ret)
        sim_max_dds.append(max_dd)

    var_95 = np.percentile(sim_max_dds, 95) * 100 # 95th percentile Drawdown
    avg_ret = np.mean(sim_returns) * 100

    return avg_ret, var_95

def run_leaderboard():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    # 58 Days Lookback (Yahoo Finance 15m limit is 60 days)
    lookback_days = 58
    end_date_obj = datetime.now()
    start_date_obj = end_date_obj - timedelta(days=lookback_days)

    # Split 70/30
    split_days = int(lookback_days * 0.7)
    split_date_obj = start_date_obj + timedelta(days=split_days)

    # Date Strings
    start_str = start_date_obj.strftime("%Y-%m-%d")
    split_str = split_date_obj.strftime("%Y-%m-%d")
    end_str = end_date_obj.strftime("%Y-%m-%d")

    logger.info(f"Backtest Configuration:")
    logger.info(f"  Total Period: {start_str} to {end_str}")
    logger.info(f"  Train Period (In-Sample): {start_str} to {split_str}")
    logger.info(f"  Test Period (Out-of-Sample): {split_str} to {end_str}")

    final_results = []

    for strat_config in STRATEGIES:
        logger.info(f"Processing Strategy: {strat_config['name']}...")

        module = load_strategy_module(strat_config['file'])
        if not module:
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"Strategy {strat_config['name']} does not have 'generate_signal' function. Skipping.")
            continue

        # 1. Optimization Phase (In-Sample)
        logger.info(f"--- Optimization Phase ({start_str} to {split_str}) ---")

        runs = [{"name": strat_config['name'], "params": None}]
        if strat_config['name'] in TUNING_CONFIG:
            variants = generate_variants(strat_config['name'], TUNING_CONFIG[strat_config['name']])
            runs.extend(variants)

        best_sharpe = -float('inf')
        best_run = runs[0]

        for run in runs:
            # Create Wrapper
            original_gen = module.generate_signal
            params = run['params']

            # Helper to create bound wrapper
            def make_wrapper(p):
                def wrapped_gen(df, client=None, symbol=None):
                    return original_gen(df, client, symbol, params=p)
                return wrapped_gen

            if params:
                wrapper_func = make_wrapper(params)

                class ModuleWrapper:
                    pass
                wrapper = ModuleWrapper()
                wrapper.generate_signal = wrapper_func
                wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
                wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)
                # Propagate check_exit if exists
                if hasattr(module, 'check_exit'):
                    wrapper.check_exit = module.check_exit
                target_module = wrapper
            else:
                target_module = module

            try:
                res = engine.run_backtest(
                    strategy_module=target_module,
                    symbol=strat_config['symbol'],
                    exchange=strat_config['exchange'],
                    start_date=start_str,
                    end_date=split_str, # Train
                    interval="15m"
                )

                if 'error' in res:
                    continue

                metrics = res.get('metrics', {})
                sharpe = metrics.get('sharpe_ratio', 0)

                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_run = run

            except Exception as e:
                logger.error(f"Error optimizing {run['name']}: {e}")

        logger.info(f"Best Variant for {strat_config['name']}: {best_run['name']} (Sharpe: {best_sharpe:.2f})")

        # 2. Validation Phase (Out-of-Sample)
        logger.info(f"--- Validation Phase ({split_str} to {end_str}) ---")

        # Prepare Best Module
        original_gen = module.generate_signal
        params = best_run['params']

        def make_wrapper_final(p):
            def wrapped_gen(df, client=None, symbol=None):
                return original_gen(df, client, symbol, params=p)
            return wrapped_gen

        if params:
            wrapper_func = make_wrapper_final(params)
            class ModuleWrapper: pass
            wrapper = ModuleWrapper()
            wrapper.generate_signal = wrapper_func
            wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
            wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)
            if hasattr(module, 'check_exit'):
                wrapper.check_exit = module.check_exit
            target_module = wrapper
        else:
            target_module = module

        try:
            res = engine.run_backtest(
                strategy_module=target_module,
                symbol=strat_config['symbol'],
                exchange=strat_config['exchange'],
                start_date=split_str,
                end_date=end_str, # Test
                interval="15m"
            )

            if 'error' in res:
                logger.error(f"Validation failed for {best_run['name']}")
                continue

            metrics = res.get('metrics', {})
            trades = res.get('closed_trades', [])
            trades_pnl = [t['pnl_pct'] for t in trades if t['pnl_pct'] is not None]

            # Monte Carlo
            mc_ret, mc_dd_95 = monte_carlo_simulation(trades_pnl, num_simulations=1000)

            final_results.append({
                "strategy": best_run['name'],
                "params": best_run['params'],
                "is_optimized": True,
                "train_period": f"{start_str} to {split_str}",
                "test_period": f"{split_str} to {end_str}",
                "total_return": metrics.get('total_return_pct', 0),
                "sharpe": metrics.get('sharpe_ratio', 0),
                "drawdown": metrics.get('max_drawdown_pct', 0),
                "win_rate": metrics.get('win_rate', 0),
                "trades": res.get('total_trades', 0),
                "profit_factor": metrics.get('profit_factor', 0),
                "mc_ret_avg": mc_ret,
                "mc_dd_95": mc_dd_95
            })

        except Exception as e:
            logger.error(f"Error validating {best_run['name']}: {e}", exc_info=True)

    # Sort by Sharpe Ratio (Test)
    final_results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    # Save JSON
    with open("leaderboard.json", "w") as f:
        json.dump(final_results, f, indent=4)

    # Generate Markdown
    md = "# Strategy Leaderboard (Out-of-Sample)\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n"
    md += f"**Period:** {split_str} to {end_str} (Test Set)\n"
    md += f"**Training:** {start_str} to {split_str} (Optimization Set)\n\n"

    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades | MC 95% DD |\n"
    md += "|---|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(final_results):
        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['profit_factor']:.2f} | {r['trades']} | {r['mc_dd_95']:.2f}% |\n"

    md += "\n## Monte Carlo Risk Analysis\n"
    md += "Monte Carlo simulation (1000 runs) estimates the 95th percentile Drawdown (VaR) based on the Out-of-Sample trade distribution.\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("Leaderboard generated: LEADERBOARD.md")

if __name__ == "__main__":
    run_leaderboard()
