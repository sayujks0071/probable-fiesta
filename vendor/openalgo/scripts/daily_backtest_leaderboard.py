#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util
import yfinance as yf

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

# --- MOCK API CLIENT FOR BACKTESTING ---
class MockAPIClient:
    def history(self, symbol, exchange, start_date, end_date, interval):
        # Map symbol to YF symbol
        yf_symbol = symbol
        if symbol == 'NIFTY': yf_symbol = '^NSEI'
        elif symbol == 'BANKNIFTY': yf_symbol = '^NSEBANK'
        elif symbol == 'RELIANCE': yf_symbol = 'RELIANCE.NS'
        elif symbol == 'INFY': yf_symbol = 'INFY.NS'
        elif 'SILVER' in symbol: yf_symbol = 'SI=F'
        elif 'GOLD' in symbol: yf_symbol = 'GC=F'
        elif 'CRUDE' in symbol: yf_symbol = 'CL=F'

        logger.info(f"Fetching mock data for {symbol} (YF: {yf_symbol})")

        try:
            # Adjust interval for YF (YF supports 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            yf_interval = interval
            if interval == 'day': yf_interval = '1d'

            data = yf.download(yf_symbol, start=start_date, end=end_date, interval=yf_interval, progress=False)

            if data.empty:
                logger.warning(f"No data for {yf_symbol}")
                return pd.DataFrame()

            # Normalize columns
            data.columns = [c.lower() for c in data.columns]
            if 'date' in data.columns:
                data = data.rename(columns={'date': 'datetime'})

            return data
        except Exception as e:
            logger.error(f"YF Download failed: {e}")
            return pd.DataFrame()

# Monkeypatch load_historical_data
def mock_load_historical_data(self, symbol, exchange, start_date, end_date, interval="15m"):
    client = MockAPIClient()
    df = client.history(symbol, exchange, start_date, end_date, interval)
    if df.empty:
        return df

    # Ensure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df

SimpleBacktestEngine.load_historical_data = mock_load_historical_data
# ---------------------------------------

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

# Initial Tuning Config (Base)
TUNING_CONFIG = {
    "SuperTrend_VWAP": {
        "stop_pct": [1.5],
        "threshold": [150]
    },
    "MCX_Momentum": {
        "adx_threshold": [25],
        "period_rsi": [14]
    },
    "AI_Hybrid": {
        "rsi_lower": [30],
        "rsi_upper": [60]
    },
    "ML_Momentum": {
        "threshold": [0.01]
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
            "name": f"{base_name}_v{i+1}" if i > 0 else base_name,
            "params": params,
            "is_variant": i > 0
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

def run_backtest_for_config(engine, module, strat_config, run_config, start_date, end_date):
    logger.info(f"  > Run: {run_config['name']} Params: {run_config['params']}")

    original_gen = module.generate_signal
    params = run_config['params']

    # Wrap generate_signal to inject params
    def wrapped_gen(df, client=None, symbol=None):
        return original_gen(df, client, symbol, params=params)

    class ModuleWrapper:
        pass
    wrapper = ModuleWrapper()
    wrapper.generate_signal = wrapped_gen
    wrapper.ATR_SL_MULTIPLIER = getattr(module, 'ATR_SL_MULTIPLIER', 1.5)
    wrapper.ATR_TP_MULTIPLIER = getattr(module, 'ATR_TP_MULTIPLIER', 2.5)

    try:
        res = engine.run_backtest(
            strategy_module=wrapper,
            symbol=strat_config['symbol'],
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
            "base_strategy": strat_config['name'],
            "params": run_config['params'],
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

def optimize_strategies(engine, results, start_date, end_date):
    logger.info("\n=== Starting Optimization Loop ===")

    # Select top 3 strategies by Sharpe
    # Filter out variants first to get base strategies?
    # Current results only have base runs (from TUNING_CONFIG single entry)

    top_3 = sorted(results, key=lambda x: x['sharpe'], reverse=True)[:3]

    optimized_results = []

    for res in top_3:
        strat_name = res['base_strategy'] # We need base name
        logger.info(f"Optimizing {strat_name}...")

        # Find config
        strat_config = next((s for s in STRATEGIES if s['name'] == strat_name), None)
        if not strat_config: continue

        module = load_strategy_module(strat_config['file'])
        if not module: continue

        # Generate variants dynamically
        # Simple perturbation: +/- 10% on numeric params
        base_params = res['params']
        if not base_params: continue

        variants = []
        import copy

        # Generate 3 variants
        # Variant 1: +10% on first param
        # Variant 2: -10% on first param
        # Variant 3: +10% on second param (if exists)

        keys = list(base_params.keys())

        # Variant 1
        v1_params = copy.deepcopy(base_params)
        k1 = keys[0]
        if isinstance(v1_params[k1], (int, float)):
            v1_params[k1] = v1_params[k1] * 1.1
            variants.append({"name": f"{strat_name}_opt_v1", "params": v1_params})

        # Variant 2
        v2_params = copy.deepcopy(base_params)
        if isinstance(v2_params[k1], (int, float)):
            v2_params[k1] = v2_params[k1] * 0.9
            variants.append({"name": f"{strat_name}_opt_v2", "params": v2_params})

        # Variant 3
        if len(keys) > 1:
            v3_params = copy.deepcopy(base_params)
            k2 = keys[1]
            if isinstance(v3_params[k2], (int, float)):
                v3_params[k2] = v3_params[k2] * 1.1
                variants.append({"name": f"{strat_name}_opt_v3", "params": v3_params})

        for variant in variants:
            opt_res = run_backtest_for_config(engine, module, strat_config, variant, start_date, end_date)
            if opt_res:
                optimized_results.append(opt_res)

    return optimized_results

def run_leaderboard():
    engine = SimpleBacktestEngine(initial_capital=100000.0)

    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    results = []

    # 1. Run Base Strategies
    logger.info("--- Phase 1: Base Strategy Backtest ---")
    for strat_config in STRATEGIES:
        logger.info(f"Backtesting {strat_config['name']}...")

        module = load_strategy_module(strat_config['file'])
        if not module: continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"Strategy {strat_config['name']} does not have 'generate_signal' function. Skipping.")
            continue

        # Use base params from TUNING_CONFIG (single value lists)
        base_grid = TUNING_CONFIG.get(strat_config['name'], {})
        # Flatten to single dict
        base_params = {k: v[0] for k, v in base_grid.items()} if base_grid else {}

        run_config = {"name": strat_config['name'], "params": base_params}

        res = run_backtest_for_config(engine, module, strat_config, run_config, start_date, end_date)
        if res:
            results.append(res)

    # 2. Optimize
    if results:
        opt_results = optimize_strategies(engine, results, start_date, end_date)
        results.extend(opt_results)

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
