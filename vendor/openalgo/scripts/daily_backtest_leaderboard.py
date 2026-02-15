#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
import importlib.util

# Add repo root to path (vendor/openalgo)
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)
# Add vendor path to allow 'import openalgo'
sys.path.append(os.path.dirname(repo_root))

# Import dependencies
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    # Fallback
    sys.path.append(os.path.join(repo_root, 'openalgo'))
    from strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    from strategies.utils.symbol_resolver import SymbolResolver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

CONFIG_FILE = os.path.join(repo_root, 'strategies/active_strategies.json')

TUNING_CONFIG = {
    "SuperTrend_VWAP": {
        "stop_pct": [1.5, 2.0],
        "threshold": [140, 160]
    },
    "MCX_Momentum": {
        "adx_threshold": [20, 25],
        "period_rsi": [10, 14]
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
    if not os.path.exists(filepath):
        logger.error(f"Strategy file not found: {filepath}")
        return None
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def resolve_symbol(config, resolver):
    try:
        res = resolver.resolve(config)
        if isinstance(res, dict):
            return res.get('sample_symbol')
        return res
    except Exception as e:
        logger.error(f"Resolution failed for {config.get('underlying')}: {e}")
        return None

def run_leaderboard():
    logger.info("Starting Backtest Leaderboard Generation...")

    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)

    resolver = SymbolResolver()
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d") # Short period for daily test
    end_date = datetime.now().strftime("%Y-%m-%d")

    results = []

    for strat_id, config in configs.items():
        logger.info(f"Processing {strat_id}...")

        # Resolve Symbol
        symbol = resolve_symbol(config, resolver)
        if not symbol:
            logger.warning(f"Skipping {strat_id}: Could not resolve symbol.")
            continue

        logger.info(f"  > Symbol: {symbol}")

        # Locate Strategy File
        # config['strategy'] contains module name like 'orb_strategy'
        # We assume they are in strategies/scripts/
        strat_name = config.get('strategy')
        # Handle full path or just name
        if strat_name.endswith('.py'):
            script_path = os.path.join(repo_root, 'strategies/scripts', strat_name)
        else:
            script_path = os.path.join(repo_root, 'strategies/scripts', f"{strat_name}.py")

        module = load_strategy_module(script_path)
        if not module:
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"  > No generate_signal in {strat_name}. Skipping.")
            continue

        # Prepare runs (Base + Variants)
        runs = [{"name": strat_id, "params": config.get('params', {})}]

        # Check for tuning config matching generic strategy name
        # Mapping: config['strategy'] might match TUNING_CONFIG keys?
        # or config key (strat_id)?
        # Let's check config['strategy'] for tuning
        base_strat_key = None
        if "supertrend" in strat_name: base_strat_key = "SuperTrend_VWAP"
        elif "mcx" in strat_name: base_strat_key = "MCX_Momentum"

        if base_strat_key and base_strat_key in TUNING_CONFIG:
            variants = generate_variants(base_strat_key, TUNING_CONFIG[base_strat_key])
            # Limit variants to avoid explosion
            runs.extend(variants[:3])

        for run in runs:
            run_name = run['name']
            if run.get('is_variant'):
                run_name = f"{strat_id} ({run['name']})"

            logger.info(f"  > Backtesting: {run_name}")

            # Wrap module to inject params
            original_gen = module.generate_signal
            run_params = run['params']

            # Wrapper
            def wrapped_gen(df, client=None, symbol=None):
                return original_gen(df, client, symbol, params=run_params)

            # Create Mock Module Object
            class ModuleWrapper:
                pass
            wrapper = ModuleWrapper()
            wrapper.generate_signal = wrapped_gen
            # Copy attributes if needed
            wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
            wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)
            wrapper.TIME_STOP_BARS = getattr(module, 'TIME_STOP_BARS', 12)
            wrapper.BREAKEVEN_TRIGGER_R = getattr(module, 'BREAKEVEN_TRIGGER_R', 1.0)

            try:
                res = engine.run_backtest(
                    strategy_module=wrapper,
                    symbol=symbol,
                    exchange=config.get('exchange', 'NSE'), # Might need adjustment for Indices
                    start_date=start_date,
                    end_date=end_date,
                    interval="15m"
                )

                if 'error' in res:
                    logger.error(f"    Failed: {res['error']}")
                    continue

                metrics = res.get('metrics', {})
                results.append({
                    "strategy": run_name,
                    "symbol": symbol,
                    "params": str(run_params),
                    "total_return": metrics.get('total_return_pct', 0),
                    "sharpe": metrics.get('sharpe_ratio', 0),
                    "drawdown": metrics.get('max_drawdown_pct', 0),
                    "win_rate": metrics.get('win_rate', 0),
                    "trades": res.get('total_trades', 0),
                    "profit_factor": metrics.get('profit_factor', 0)
                })

            except Exception as e:
                logger.error(f"    Exception: {e}", exc_info=True)

    # Generate Report
    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    output_dir = os.path.dirname(CONFIG_FILE) # openalgo/strategies/
    json_path = os.path.join(output_dir, "leaderboard.json")
    md_path = os.path.join(output_dir, "LEADERBOARD.md")

    with open(json_path, "w") as f:
        json.dump(results, f, indent=4)

    md = "# Daily Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n"
    md += f"**Period:** {start_date} to {end_date}\n\n"
    md += "| Rank | Strategy | Symbol | Sharpe | Return % | Drawdown % | Win Rate % | Trades |\n"
    md += "|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy']} | {r['symbol']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['trades']} |\n"

    with open(md_path, "w") as f:
        f.write(md)

    logger.info(f"Leaderboard generated: {md_path}")

if __name__ == "__main__":
    run_leaderboard()
