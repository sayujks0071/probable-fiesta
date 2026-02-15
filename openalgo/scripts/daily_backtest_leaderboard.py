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

TUNING_CONFIG = {
    "supertrend_vwap_strategy": {
        "stop_pct": [1.5, 2.0],
        "threshold": [140, 150, 160]
    },
    "mcx_commodity_momentum_strategy": {
        "adx_threshold": [20, 25, 30],
        "period_rsi": [10, 14]
    },
    "ai_hybrid_reversion_breakout": {
        "rsi_lower": [25, 30, 35],
        "rsi_upper": [60, 65, 70]
    },
    "advanced_ml_momentum_strategy": {
        "threshold": [0.01, 0.015, 0.02]
    }
}

def load_active_strategies():
    strategies = []
    config_path = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')
    if not os.path.exists(config_path):
        logger.warning("No active_strategies.json found.")
        return []

    try:
        with open(config_path, 'r') as f:
            configs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load active_strategies.json: {e}")
        return []

    try:
        resolver = SymbolResolver()
    except Exception as e:
        logger.warning(f"SymbolResolver init failed: {e}")
        resolver = None

    for name, cfg in configs.items():
        script = cfg.get('strategy')
        if not script:
            continue

        filepath = os.path.join(repo_root, f'openalgo/strategies/scripts/{script}.py')
        if not os.path.exists(filepath):
            logger.warning(f"Strategy script not found: {filepath}")
            continue

        # Resolve Symbol
        symbol = None
        if resolver:
            try:
                symbol = resolver.resolve_symbol(cfg)
            except Exception as e:
                logger.warning(f"Symbol resolution failed for {name}: {e}")

        if not symbol:
            symbol = cfg.get('symbol', cfg.get('underlying', 'NIFTY'))

        strategies.append({
            "name": name,
            "file": filepath,
            "symbol": symbol,
            "exchange": cfg.get('exchange', 'NSE'),
            "base_strategy": script
        })
    return strategies

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
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def run_leaderboard():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    # Use 3-5 days for quick daily test
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    results = []

    strategies = load_active_strategies()
    if not strategies:
        logger.warning("No strategies to backtest.")
        return

    for strat_config in strategies:
        logger.info(f"Backtesting {strat_config['name']} ({strat_config['symbol']})...")

        module = load_strategy_module(strat_config['file'])
        if not module:
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"Strategy {strat_config['name']} does not have 'generate_signal' function. Skipping.")
            continue

        # Determine variants to run
        runs = [{"name": strat_config['name'], "params": None}]

        base_script = strat_config.get('base_strategy')
        if base_script in TUNING_CONFIG:
            # Generate small set of variants
            variants = generate_variants(strat_config['name'], TUNING_CONFIG[base_script])
            # Limit to 3 variants to save time
            runs.extend(variants[:3])

        for run in runs:
            logger.info(f"  > Variant: {run['name']} Params: {run['params']}")

            original_gen = module.generate_signal

            # Create a partial/wrapper
            params = run['params']
            if params:
                def wrapped_gen(df, client=None, symbol=None):
                    return original_gen(df, client, symbol, params=params)

                class ModuleWrapper:
                    pass
                wrapper = ModuleWrapper()
                wrapper.generate_signal = wrapped_gen
                # Copy attributes
                for attr in ['ATR_SL_MULTIPLIER', 'ATR_TP_MULTIPLIER', 'TIME_STOP_BARS']:
                    if hasattr(module, attr):
                        setattr(wrapper, attr, getattr(module, attr))

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
                    interval="15m" # Default interval
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
    results.sort(key=lambda x: (x.get('sharpe', -99), x.get('total_return', -99)), reverse=True)

    # Save JSON
    with open("leaderboard.json", "w") as f:
        json.dump(results, f, indent=4)

    # Generate Markdown
    md = "# Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Profit Factor | Trades |\n"
    md += "|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        sharpe = r.get('sharpe', 0)
        ret = r.get('total_return', 0)
        dd = r.get('drawdown', 0)
        wr = r.get('win_rate', 0)
        pf = r.get('profit_factor', 0)
        trades = r.get('trades', 0)

        md += f"| {i+1} | {r['strategy']} | {sharpe:.2f} | {ret:.2f}% | {dd:.2f}% | {wr:.2f}% | {pf:.2f} | {trades} |\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("Leaderboard generated: LEADERBOARD.md")

if __name__ == "__main__":
    run_leaderboard()
