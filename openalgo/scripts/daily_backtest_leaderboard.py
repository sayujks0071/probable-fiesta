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

from openalgo.strategies.utils.symbol_resolver import SymbolResolver

# Import Backtest Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

REPORT_DIR = os.path.join(repo_root, "openalgo", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# Define Strategies with Abstract Underlying
STRATEGIES = [
    {
        "name": "SuperTrend_VWAP",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE"
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
        "underlying": "RELIANCE",
        "type": "EQUITY",
        "exchange": "NSE"
    },
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE"
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

def run_leaderboard():
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    resolver = SymbolResolver()

    # Changed from 3 days to 5 days per review feedback
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    results = []

    for strat_config in STRATEGIES:
        logger.info(f"Preparing {strat_config['name']}...")

        # Resolve Symbol
        try:
            resolved = resolver.resolve({
                'underlying': strat_config['underlying'],
                'type': strat_config['type'],
                'exchange': strat_config['exchange']
            })

            if not resolved:
                logger.error(f"Could not resolve symbol for {strat_config['name']}")
                continue

            if isinstance(resolved, dict) and 'sample_symbol' in resolved:
                symbol = resolved['sample_symbol']
            elif isinstance(resolved, str):
                symbol = resolved
            else:
                logger.error(f"Ambiguous resolution for {strat_config['name']}: {resolved}")
                continue

            logger.info(f"Resolved {strat_config['underlying']} -> {symbol}")

        except Exception as e:
            logger.error(f"Resolution failed for {strat_config['name']}: {e}")
            continue

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
            # Limit to top 2 variants to save time
            runs.extend(variants[:2])

        for run in runs:
            logger.info(f"  > Backtesting Variant: {run['name']} Params: {run['params']}")

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
                # Copy module attributes if needed
                if hasattr(module, 'ATR_SL_MULTIPLIER'): wrapper.ATR_SL_MULTIPLIER = module.ATR_SL_MULTIPLIER
                if hasattr(module, 'ATR_TP_MULTIPLIER'): wrapper.ATR_TP_MULTIPLIER = module.ATR_TP_MULTIPLIER
                if hasattr(module, 'TIME_STOP_BARS'): wrapper.TIME_STOP_BARS = module.TIME_STOP_BARS

                target_module = wrapper
            else:
                target_module = module

            try:
                # Run Backtest
                res = engine.run_backtest(
                    strategy_module=target_module,
                    symbol=symbol,
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
                    "symbol": symbol,
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
    json_path = os.path.join(REPORT_DIR, "leaderboard.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=4)

    # Generate Markdown
    md = "# Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md += "| Rank | Strategy | Symbol | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades |\n"
    md += "|---|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy']} | {r['symbol']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['profit_factor']:.2f} | {r['trades']} |\n"

    md_path = os.path.join(REPORT_DIR, "LEADERBOARD.md")
    with open(md_path, "w") as f:
        f.write(md)

    logger.info(f"Leaderboard generated: {md_path}")

if __name__ == "__main__":
    run_leaderboard()
