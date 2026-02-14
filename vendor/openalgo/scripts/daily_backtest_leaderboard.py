#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util
import itertools

# Add repo root (vendor) to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, 'vendor'))

# OpenAlgo Imports
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    # Fallback
    sys.path.append(os.path.join(repo_root, 'vendor', 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine
    from symbol_resolver import SymbolResolver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

CONFIG_FILE = os.path.join(repo_root, 'vendor', 'openalgo', 'strategies', 'active_strategies.json')

TUNING_GRID = {
    "supertrend_vwap_strategy": {
        "threshold": [140, 150, 160],
        "stop_pct": [1.5, 1.8, 2.0],
        "adx_threshold": [20, 25]
    },
    "mcx_commodity_momentum_strategy": {
        "period_rsi": [10, 14],
        "adx_threshold": [20, 25, 30]
    }
}

def load_active_strategies():
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

        for strat_id, conf in configs.items():
            script_name = conf.get('strategy')
            if not script_name: continue

            # Construct file path
            file_path = os.path.join(repo_root, 'vendor', 'openalgo', 'strategies', 'scripts', f"{script_name}.py")

            # Determine exchange
            exchange = conf.get('exchange', 'NSE')
            if exchange == 'NSE' and conf.get('type') == 'EQUITY' and 'NIFTY' in conf.get('underlying', ''):
                exchange = 'NSE_INDEX'

            strategies.append({
                "name": strat_id,
                "file": file_path,
                "config": conf,
                "symbol": conf.get('symbol') or conf.get('underlying'),
                "exchange": exchange
            })
    except Exception as e:
        logger.error(f"Error loading active strategies: {e}")

    return strategies

def load_strategy_module(filepath):
    """Load a strategy script as a module."""
    try:
        if not os.path.exists(filepath):
            # Try finding relative to repo root
            filepath = os.path.join(repo_root, filepath)

        if not os.path.exists(filepath):
            logger.error(f"Strategy file not found: {filepath}")
            return None

        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def resolve_symbol(config):
    try:
        resolver = SymbolResolver()
        res = resolver.resolve(config)
        if isinstance(res, dict):
            return res.get('sample_symbol')
        return res
    except Exception as e:
        logger.warning(f"Symbol resolution failed: {e}")
        return None

def generate_variants(base_name, grid):
    keys = list(grid.keys())
    values = list(grid.values())
    combinations = list(itertools.product(*values))

    variants = []
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        variants.append({
            "name": f"{base_name}_v{i+1}",
            "params": params,
            "is_variant": True,
            "base_strategy": base_name
        })
    return variants

def run_backtest_pipeline():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    # 5 Days History for Daily Test
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    results = []
    strategies = load_active_strategies()

    # 1. Base Strategies
    for strat_config in strategies:
        logger.info(f"--- Processing {strat_config['name']} ---")

        # Resolve Symbol
        symbol = resolve_symbol(strat_config['config']) or strat_config['symbol']
        exchange = strat_config['exchange']
        logger.info(f"Using Symbol: {symbol} on {exchange}")

        module = load_strategy_module(strat_config['file'])
        if not module or not hasattr(module, 'generate_signal'):
            logger.warning(f"Invalid module: {strat_config['name']} ({strat_config['file']})")
            continue

        # Run Base
        res = run_single_backtest(engine, module, symbol, exchange, start_date, end_date, None)
        if res:
            res['strategy'] = strat_config['name']
            res['is_variant'] = False
            results.append(res)

            # 2. Tuning Loop (Fine-tune)
            script_name = strat_config['config'].get('strategy')
            if script_name in TUNING_GRID:
                logger.info(f"  > Tuning {script_name}...")
                variants = generate_variants(strat_config['name'], TUNING_GRID[script_name])

                for variant in variants:
                    v_res = run_single_backtest(engine, module, symbol, exchange, start_date, end_date, variant['params'])
                    if v_res:
                        v_res['strategy'] = variant['name']
                        v_res['is_variant'] = True
                        v_res['params'] = variant['params']
                        results.append(v_res)

    # 3. Rank & Report
    rank_and_report(results)

def run_single_backtest(engine, module, symbol, exchange, start, end, params):
    try:
        # Wrap generate_signal to inject params
        original_gen = module.generate_signal

        # Dynamic Wrapper Class to mimic module structure expected by Engine?
        # Engine expects 'strategy_module' which has 'generate_signal'.
        # We can pass an object.

        class StrategyWrapper:
            def __init__(self, p):
                self.params = p
                # Copy module constants if needed
                self.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
                self.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)

            def generate_signal(self, df, client=None, sym=None):
                # Call original with params
                # Note: module.generate_signal(df, client, symbol, params=params)
                # But engine calls: strategy_module.generate_signal(df, client, symbol)
                # So we ignore extra args engine might pass or not pass
                return original_gen(df, client, sym, params=self.params)

        wrapper = StrategyWrapper(params)

        res = engine.run_backtest(
            strategy_module=wrapper,
            symbol=symbol,
            exchange=exchange,
            start_date=start,
            end_date=end,
            interval="15m" # Default
        )

        if 'error' in res:
            logger.warning(f"Backtest Error: {res['error']}")
            return None

        metrics = res.get('metrics', {})
        return {
            "total_return": metrics.get('total_return_pct', 0),
            "sharpe": metrics.get('sharpe_ratio', 0),
            "drawdown": metrics.get('max_drawdown_pct', 0),
            "win_rate": metrics.get('win_rate', 0),
            "trades": res.get('total_trades', 0),
            "profit_factor": metrics.get('profit_factor', 0)
        }

    except Exception as e:
        logger.error(f"Backtest Exception: {e}", exc_info=True)
        return None

def rank_and_report(results):
    if not results:
        logger.warning("No results to report.")
        return

    # Sort: Primary Sharpe, Secondary Return
    # Penalize low trade count (< 5)
    def score(r):
        s = r['sharpe']
        if r['trades'] < 3: s -= 1.0 # Penalty
        return (s, r['total_return'])

    results.sort(key=score, reverse=True)

    # JSON Output
    report_file_json = "leaderboard.json"
    with open(report_file_json, "w") as f:
        json.dump(results, f, indent=4)

    # Markdown Output
    report_file_md = "LEADERBOARD.md"
    md = "# 🏆 OpenAlgo Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    md += "| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Trades | Params |\n"
    md += "|---|---|---|---|---|---|---|---|\n"

    top_picks = []

    for i, r in enumerate(results):
        params_str = str(r.get('params', 'Default')) if r.get('is_variant') else "Default"
        # Shorten params string
        if len(params_str) > 50: params_str = "Custom"

        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['trades']} | {params_str} |\n"

        if i < 3:
            top_picks.append(r)

    md += "\n## 🚀 Top Recommendations\n\n"
    for pick in top_picks:
        md += f"- **{pick['strategy']}**: Sharpe {pick['sharpe']:.2f}, Return {pick['total_return']:.2f}%. "
        if pick.get('is_variant'):
            md += f"Optimized Params: `{pick['params']}`\n"
        else:
            md += "Using Default Logic.\n"

    with open(report_file_md, "w") as f:
        f.write(md)

    logger.info(f"Leaderboard generated: {report_file_md}, {report_file_json}")

if __name__ == "__main__":
    run_backtest_pipeline()
