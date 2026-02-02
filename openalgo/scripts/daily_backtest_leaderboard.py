#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
import importlib.util
import itertools

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import Backtest Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine
    from symbol_resolver import SymbolResolver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

STRATEGIES = [
    {
        "name": "SuperTrend_VWAP",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "MCX_Momentum",
        "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
        "underlying": "SILVER",
        "type": "FUT",
        "exchange": "MCX"
    },
    {
        "name": "AI_Hybrid",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE_INDEX"
    }
]

TUNING_CONFIG = {
    "SuperTrend_VWAP": {
        "stop_pct": [1.5, 2.0],
        "threshold": [150, 160]
    },
    "MCX_Momentum": {
        "adx_threshold": [20, 25, 30],
        "period_rsi": [10, 14]
    },
    "AI_Hybrid": {
        "rsi_lower": [25, 30, 35],
        "rsi_upper": [60, 70]
    },
    "ML_Momentum": {
        "threshold": [0.01, 0.015, 0.02]
    }
}

def generate_variants(base_name, grid, limit=3):
    keys = list(grid.keys())
    values = list(grid.values())
    combinations = list(itertools.product(*values))

    variants = []
    for i, combo in enumerate(combinations):
        if i >= limit: break # Limit variants
        params = dict(zip(keys, combo))
        variants.append({
            "name": f"{base_name}_v{i+1}",
            "params": params,
            "is_variant": True,
            "base_name": base_name
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

def resolve_symbol(strat_config, resolver):
    if 'symbol' in strat_config:
        return strat_config['symbol']

    if 'underlying' in strat_config:
        res = resolver.resolve(strat_config)
        if isinstance(res, dict):
            return res.get('sample_symbol')
        return res
    return "TEST"

def run_backtest_for_strategy(engine, module, strat_config, run_config, start_date, end_date):
    """
    Run backtest for a single strategy variant.
    """
    # Create wrapper for params
    original_gen = module.generate_signal
    params = run_config.get('params')

    # Define wrapper
    def wrapped_gen(df, client=None, symbol=None):
        return original_gen(df, client, symbol, params=params)

    # Create module-like object
    class ModuleWrapper:
        pass
    wrapper = ModuleWrapper()
    wrapper.generate_signal = wrapped_gen

    # Copy attributes likely needed by Engine
    for attr in ['ATR_SL_MULTIPLIER', 'ATR_TP_MULTIPLIER', 'TIME_STOP_BARS', 'BREAKEVEN_TRIGGER_R']:
        if hasattr(module, attr):
            setattr(wrapper, attr, getattr(module, attr))

    # Resolve symbol
    symbol = strat_config.get('resolved_symbol')

    try:
        res = engine.run_backtest(
            strategy_module=wrapper,
            symbol=symbol,
            exchange=strat_config['exchange'],
            start_date=start_date,
            end_date=end_date,
            interval="15m"
        )

        if 'error' in res:
            logger.error(f"Backtest failed for {run_config['name']}: {res['error']}")
            return None

        metrics = res.get('metrics', {})
        return {
            "strategy": run_config['name'],
            "base_strategy": run_config.get('base_name', run_config['name']),
            "params": params,
            "total_return": metrics.get('total_return_pct', 0),
            "sharpe": metrics.get('sharpe_ratio', 0),
            "drawdown": metrics.get('max_drawdown_pct', 0),
            "win_rate": metrics.get('win_rate', 0),
            "trades": res.get('total_trades', 0),
            "profit_factor": metrics.get('profit_factor', 0)
        }

    except Exception as e:
        logger.error(f"Error backtesting {run_config['name']}: {e}", exc_info=True)
        return None

def run_leaderboard():
    logger.info("Starting Daily Backtest & Tuning Loop...")
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    resolver = SymbolResolver()

    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    # 1. Resolve Symbols & Verify Modules
    valid_strategies = []
    for s in STRATEGIES:
        s['resolved_symbol'] = resolve_symbol(s, resolver)
        s['module'] = load_strategy_module(s['file'])
        if s['module'] and hasattr(s['module'], 'generate_signal'):
            valid_strategies.append(s)
            logger.info(f"Loaded {s['name']} (Symbol: {s['resolved_symbol']})")
        else:
            logger.warning(f"Skipping {s['name']}: Module invalid or missing generate_signal")

    # 2. Run Base Strategies
    results = []
    for s in valid_strategies:
        logger.info(f"Running Base: {s['name']}")
        res = run_backtest_for_strategy(engine, s['module'], s, {"name": s['name'], "params": None}, start_date, end_date)
        if res: results.append(res)

    # 3. Rank and Select Top 3
    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)
    top_strategies = results[:3]
    logger.info(f"Top 3 Strategies selected for tuning: {[r['strategy'] for r in top_strategies]}")

    # 4. Generate & Run Variants for Top 3
    tuned_results = []
    for r in top_strategies:
        base_name = r['strategy']
        if base_name in TUNING_CONFIG:
            logger.info(f"Tuning {base_name}...")
            variants = generate_variants(base_name, TUNING_CONFIG[base_name], limit=3)

            # Find the strat config
            strat_config = next(s for s in valid_strategies if s['name'] == base_name)

            for v in variants:
                logger.info(f"  > Variant: {v['name']} Params: {v['params']}")
                res = run_backtest_for_strategy(engine, strat_config['module'], strat_config, v, start_date, end_date)
                if res: tuned_results.append(res)
        else:
            logger.info(f"No tuning config for {base_name}")

    # 5. Merge & Final Leaderboard
    final_results = results + tuned_results
    final_results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    # Save JSON
    with open("leaderboard.json", "w") as f:
        json.dump(final_results, f, indent=4)

    # Generate Markdown
    md = "# Strategy Leaderboard (with Tuning)\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades | Params |\n"
    md += "|---|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(final_results):
        param_str = str(r['params']) if r['params'] else "-"
        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['profit_factor']:.2f} | {r['trades']} | {param_str} |\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("Leaderboard generated: LEADERBOARD.md")

if __name__ == "__main__":
    run_leaderboard()
