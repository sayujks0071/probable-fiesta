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

# Import Utils
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    from openalgo.strategies.utils.trading_utils import APIClient
except ImportError:
    vendor_path = os.path.join(repo_root, 'vendor', 'openalgo')
    sys.path.append(vendor_path)
    try:
        from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
        from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        from openalgo.strategies.utils.trading_utils import APIClient
    except ImportError:
        # Local fallback
        sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
        from simple_backtest_engine import SimpleBacktestEngine
        from symbol_resolver import SymbolResolver
        from trading_utils import APIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Leaderboard")

STRATEGY_MAP = {
    "supertrend_vwap_strategy": "supertrend_vwap_strategy.py",
    "ai_hybrid_reversion_breakout": "ai_hybrid_reversion_breakout.py",
    "mcx_commodity_momentum_strategy": "mcx_commodity_momentum_strategy.py",
    "advanced_ml_momentum_strategy": "advanced_ml_momentum_strategy.py",
    "gap_fade_strategy": "gap_fade_strategy.py"
}

def load_active_strategies():
    path = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')
    if not os.path.exists(path):
        logger.warning("active_strategies.json not found")
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load active strategies: {e}")
        return {}

def load_strategy_module(filename):
    """Load a strategy script as a module."""
    filepath = os.path.join(repo_root, 'openalgo/strategies/scripts', filename)
    if not os.path.exists(filepath):
        logger.warning(f"Strategy file not found: {filepath}")
        return None

    try:
        module_name = filename.replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filename}: {e}")
        return None

def run_leaderboard():
    logger.info("=== STARTING BACKTEST LEADERBOARD ===")

    configs = load_active_strategies()
    resolver = SymbolResolver()

    # Initialize Engine
    # We use a mocked API Key since backtest usually mocks data or fetches historical
    engine = SimpleBacktestEngine(initial_capital=100000.0, api_key="BACKTEST")

    # Start/End dates (Last 30 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    results = []

    for strat_id, config in configs.items():
        strat_name = config.get('strategy')
        if strat_name not in STRATEGY_MAP:
            logger.warning(f"Unknown strategy script for {strat_id} ({strat_name})")
            continue

        filename = STRATEGY_MAP[strat_name]
        module = load_strategy_module(filename)
        if not module: continue

        # Check if module has generate_signal
        if not hasattr(module, 'generate_signal'):
             logger.warning(f"Strategy {filename} missing 'generate_signal'. Skipping.")
             continue

        # Resolve Symbol
        # Backtest needs TRADABLE symbol.
        # But for mock backtest or historical, maybe underlying is enough?
        # SimpleBacktestEngine calls `client.history(symbol...)`.
        # If we use APIClient, we need valid symbol.

        # For options, verifying backtest is hard without option data.
        # We will skip OPT strategies if data is missing or just try underlying for signal logic?
        # AI_Hybrid uses 'NIFTY 50' underlying for data.

        resolved_symbol = resolver.get_tradable_symbol(config)
        # If resolved is None (e.g. Option not found in mock/real), try underlying
        # Strategy logic usually expects symbol to be what it trades.

        # For this exercise, we prioritize the Resolved Symbol.
        # If it fails, we fall back to config['underlying'] if Type is EQUITY/FUT.

        test_symbol = resolved_symbol
        if not test_symbol:
            test_symbol = config.get('underlying') or config.get('symbol')

        if not test_symbol:
            logger.warning(f"Could not resolve symbol for {strat_id}. Skipping.")
            continue

        logger.info(f"Backtesting {strat_id} ({strat_name}) on {test_symbol}...")

        exchange = config.get('exchange', 'NSE')

        try:
            # Run Backtest
            # We pass config params to generate_signal if supported
            # Most strategies don't support dynamic params in generate_signal yet (except my MCX refactor)
            # We rely on strategy defaults or arguments injection?

            # Monkey patch params if module supports 'DEFAULT_PARAMS' or similar?
            # Or assume strategy handles itself.

            res = engine.run_backtest(
                strategy_module=module,
                symbol=test_symbol,
                exchange=exchange,
                start_date=start_str,
                end_date=end_str,
                interval="15m"
            )

            if res.get('error'):
                logger.error(f"Backtest error for {strat_id}: {res['error']}")
                continue

            metrics = res.get('metrics', {})

            results.append({
                "rank_score": 0, # Placeholder
                "strategy_id": strat_id,
                "strategy_type": strat_name,
                "symbol": test_symbol,
                "sharpe": metrics.get('sharpe_ratio', 0),
                "return_pct": metrics.get('total_return_pct', 0),
                "drawdown_pct": metrics.get('max_drawdown_pct', 0),
                "win_rate": metrics.get('win_rate', 0),
                "profit_factor": metrics.get('profit_factor', 0),
                "trades": res.get('total_trades', 0)
            })

        except Exception as e:
            logger.error(f"Exception backtesting {strat_id}: {e}", exc_info=True)

    # Ranking Logic
    # Score = Sharpe * 0.4 + Return * 0.3 + (100 - DD) * 0.2 + WinRate * 0.1
    # Normalize?
    # Simple weighted sum.

    for r in results:
        # Protect against NaN
        sharpe = r['sharpe'] if pd.notna(r['sharpe']) else 0
        ret = r['return_pct'] if pd.notna(r['return_pct']) else 0
        dd = r['drawdown_pct'] if pd.notna(r['drawdown_pct']) else 0
        wr = r['win_rate'] if pd.notna(r['win_rate']) else 0

        # Max DD is negative usually? No, mostly positive % in metrics.
        # Assuming DD is positive number (e.g. 5.0%).

        score = (sharpe * 10) + (ret * 0.5) - (dd * 1.0) + (wr * 0.1)
        r['rank_score'] = round(score, 2)

    # Sort
    results.sort(key=lambda x: x['rank_score'], reverse=True)

    # Save
    with open("leaderboard.json", "w") as f:
        json.dump(results, f, indent=4)

    # Markdown
    md = "# 🏆 Daily Strategy Leaderboard\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md += "| Rank | ID | Symbol | Score | Sharpe | Return % | DD % | Win Rate % | Trades |\n"
    md += "|---|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy_id']} | {r['symbol']} | {r['rank_score']} | {r['sharpe']:.2f} | {r['return_pct']:.2f}% | {r['drawdown_pct']:.2f}% | {r['win_rate']:.2f}% | {r['trades']} |\n"

    with open("LEADERBOARD.md", "w") as f:
        f.write(md)

    logger.info("✅ Leaderboard Generated: LEADERBOARD.md")

if __name__ == "__main__":
    run_leaderboard()
