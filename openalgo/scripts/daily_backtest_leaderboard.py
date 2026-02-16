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

# Import SymbolResolver
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

CONFIG_FILE = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')
STRATEGIES_DIR = os.path.join(repo_root, 'openalgo/strategies/scripts')

TUNING_CONFIG = {
    "supertrend_vwap_strategy": {
        "stop_pct": [1.5, 2.0],
        "threshold": [150, 160]
    },
    "mcx_commodity_momentum_strategy": {
        "adx_threshold": [20, 30],
        "period_rsi": [10, 14]
    },
    "ai_hybrid_reversion_breakout": {
        "rsi_lower": [25, 35],
        "rsi_upper": [60, 70]
    },
    "advanced_ml_momentum_strategy": {
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
    if not os.path.exists(filepath):
        logger.warning(f"Strategy file not found: {filepath}")
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

def get_active_strategies():
    strategies = []

    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"Config file not found: {CONFIG_FILE}")
        return strategies

    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
            if not content.strip():
                return strategies
            configs = json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return strategies

    resolver = SymbolResolver()

    for strat_id, config in configs.items():
        strat_name = config.get('strategy')
        if not strat_name: continue

        file_path = os.path.join(STRATEGIES_DIR, f"{strat_name}.py")

        # Resolve Symbol
        res = resolver.resolve(config)
        symbol = None

        if isinstance(res, dict):
            symbol = res.get('sample_symbol') # Use sample for backtest if option
        else:
            symbol = res

        if not symbol:
            logger.warning(f"Skipping {strat_id}: Could not resolve symbol")
            continue

        strategies.append({
            "name": strat_id, # Use Config ID as name (e.g. ORB_NIFTY)
            "strategy_type": strat_name, # Script name (e.g. orb_strategy)
            "file": file_path,
            "symbol": symbol,
            "exchange": config.get('exchange', 'NSE'),
            "params": config.get('params', {})
        })

    return strategies

def run_leaderboard():
    # 1. Load Strategies
    strategies = get_active_strategies()

    if not strategies:
        logger.warning("No active strategies found to backtest.")
        return

    engine = SimpleBacktestEngine(initial_capital=100000.0)

    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    results = []

    for strat_config in strategies:
        logger.info(f"Backtesting {strat_config['name']} ({strat_config['symbol']})...")

        module = load_strategy_module(strat_config['file'])
        if not module:
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"Strategy {strat_config['name']} does not have 'generate_signal' function. Skipping.")
            continue

        # Determine variants to run
        # Include the base config from active_strategies.json
        runs = [{"name": strat_config['name'], "params": strat_config['params']}]

        # Add tuning variants if configured
        strat_type = strat_config['strategy_type']
        if strat_type in TUNING_CONFIG:
            variants = generate_variants(strat_config['name'], TUNING_CONFIG[strat_type])
            runs.extend(variants)

        for run in runs:
            logger.info(f"  > Variant: {run['name']} Params: {run['params']}")

            original_gen = module.generate_signal

            # Create a partial/wrapper
            params = run['params']

            # Helper to wrap
            def make_wrapper(func, p, mod):
                def wrapped(df, client=None, symbol=None):
                    return func(df, client, symbol, params=p)
                return wrapped

            wrapped_gen = make_wrapper(original_gen, params, module)

            # Create a temporary object acting as module
            class ModuleWrapper:
                pass
            wrapper = ModuleWrapper()
            wrapper.generate_signal = wrapped_gen
            # Copy attributes
            wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
            wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)
            wrapper.TIME_STOP_BARS = getattr(module, 'TIME_STOP_BARS', None)

            target_module = wrapper

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
    run_leaderboard()
