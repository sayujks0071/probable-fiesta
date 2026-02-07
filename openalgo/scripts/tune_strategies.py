#!/usr/bin/env python3
"""
Strategy Parameter Tuning Script
"""
import os
import sys
import json
import logging
import itertools
import pandas as pd
from datetime import datetime, timedelta

# Add repo root
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Import dependencies
try:
    from openalgo.scripts.comprehensive_backtest import MockAPIClient, SimpleBacktestEngine
except ImportError:
    sys.path.append(os.path.join(repo_root, 'openalgo', 'scripts'))
    from comprehensive_backtest import MockAPIClient
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Tuning")

STRATEGIES = {
    "advanced_ml_momentum_strategy": {
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX",
        "grid": {
            "roc_threshold": [0.01, 0.015, 0.02],
            "stop_pct": [1.5, 2.0, 2.5]
        }
    },
    "ai_hybrid_reversion_breakout": {
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX",
        "grid": {
            "rsi_lower": [30, 35, 40],
            "rsi_upper": [55, 60, 65]
        }
    }
}

def load_strategy_module(filepath):
    import importlib.util
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return None

def run_tuning():
    start_date = "2023-01-01"
    end_date = "2024-12-31"

    # Custom Engine to inject Mock Client
    class MockBacktestEngine(SimpleBacktestEngine):
        def __init__(self, initial_capital=100000.0):
            super().__init__(initial_capital=initial_capital, api_key="mock")
            self.client = MockAPIClient()

    engine = MockBacktestEngine()
    results = []

    for name, config in STRATEGIES.items():
        logger.info(f"Tuning {name}...")
        filepath = os.path.join(repo_root, config['file'])
        module = load_strategy_module(filepath)

        if not module or not hasattr(module, 'generate_signal'):
            continue

        # Generate Param Grid
        grid = config['grid']
        keys = list(grid.keys())
        values = list(grid.values())
        combinations = list(itertools.product(*values))

        logger.info(f"Testing {len(combinations)} combinations for {name}")

        for combo in combinations:
            params = dict(zip(keys, combo))
            param_str = ", ".join([f"{k}={v}" for k, v in params.items()])

            # Create a wrapper for the strategy module to inject params
            # We need to monkeypatch the module's generate_signal to accept these params
            # OR better, since generate_signal in module accepts 'params', we pass it via engine?
            # SimpleBacktestEngine calls: module.generate_signal(df, client, symbol)
            # It DOES NOT pass 'params'.
            # So we must wrap the function.

            original_func = module.generate_signal

            # Closure to capture params
            def wrapped_generate_signal(df, client=None, symbol=None):
                return original_func(df, client, symbol, params=params)

            # Temporary object to mimic module
            class ModuleWrapper:
                pass
            wrapper = ModuleWrapper()
            wrapper.generate_signal = wrapped_generate_signal
            # Copy other attributes if needed
            if hasattr(module, 'ATR_SL_MULTIPLIER'): wrapper.ATR_SL_MULTIPLIER = module.ATR_SL_MULTIPLIER
            if hasattr(module, 'ATR_TP_MULTIPLIER'): wrapper.ATR_TP_MULTIPLIER = module.ATR_TP_MULTIPLIER
            if hasattr(module, 'TIME_STOP_BARS'): wrapper.TIME_STOP_BARS = module.TIME_STOP_BARS

            try:
                res = engine.run_backtest(
                    strategy_module=wrapper,
                    symbol=config['symbol'],
                    exchange=config['exchange'],
                    start_date=start_date,
                    end_date=end_date,
                    interval="1d"
                )

                metrics = res.get('metrics', {})
                results.append({
                    "strategy": name,
                    "params": params,
                    "sharpe": metrics.get('sharpe_ratio', 0),
                    "return": metrics.get('total_return_pct', 0),
                    "trades": res.get('total_trades', 0),
                    "drawdown": metrics.get('max_drawdown_pct', 0)
                })
                logger.info(f"  > Params: {param_str} | Sharpe: {metrics.get('sharpe_ratio', 0):.2f} | Ret: {metrics.get('total_return_pct', 0):.2f}% | Trades: {res.get('total_trades', 0)}")

            except Exception as e:
                logger.error(f"Error: {e}")

    # Save Results
    with open("tuning_results.json", "w") as f:
        json.dump(results, f, indent=4)

    # Find Best per Strategy
    best_results = {}
    for r in results:
        strat = r['strategy']
        if strat not in best_results:
            best_results[strat] = r
        else:
            # Criteria: Max Sharpe (if trades > 5)
            curr = best_results[strat]
            if r['trades'] >= 5 and r['sharpe'] > curr['sharpe']:
                best_results[strat] = r
            elif curr['trades'] < 5 and r['trades'] >= 5:
                best_results[strat] = r

    print("\n🏆 BEST CONFIGURATIONS 🏆")
    for strat, res in best_results.items():
        print(f"\nStrategy: {strat}")
        print(f"Best Params: {res['params']}")
        print(f"Sharpe: {res['sharpe']:.2f}")
        print(f"Return: {res['return']:.2f}%")
        print(f"Trades: {res['trades']}")

if __name__ == "__main__":
    run_tuning()
