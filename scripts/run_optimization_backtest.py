#!/usr/bin/env python3
import os
import sys
import pandas as pd
import numpy as np
import logging
import importlib.util
from datetime import datetime, timedelta

# Setup paths
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(repo_root)
sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))

from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Optimization")

def generate_synthetic_data(days=60, regime='TREND'):
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    periods = days * 25  # 15m bars (approx 25 per day)

    start_price = 1000.0
    prices = [start_price]

    if regime == 'TREND':
        # Upward drift with noise
        drift = 0.0005
        volatility = 0.005
        for _ in range(periods):
            change = np.random.normal(drift, volatility)
            prices.append(prices[-1] * (1 + change))

    elif regime == 'RANGE':
        # Sine wave + noise
        volatility = 0.005
        for i in range(periods):
            sine_component = 20 * np.sin(i / 100) # Long cycle
            noise = np.random.normal(0, 5)
            price = start_price + sine_component + noise
            prices.append(price)

    df = pd.DataFrame(prices, columns=['close'])
    df['open'] = df['close'] * (1 + np.random.normal(0, 0.001, len(df)))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.002, len(df))))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.002, len(df))))
    df['volume'] = np.random.randint(1000, 5000, len(df))

    # Dates
    start_dt = datetime.now() - timedelta(days=days)
    dates = [start_dt + timedelta(minutes=15*i) for i in range(len(df))]
    df.index = dates
    df.index.name = 'datetime'

    return df

class MockClient:
    def __init__(self, data_map):
        self.data_map = data_map
        self.api_key = "MOCK"
        self.host = "MOCK"

    def history(self, symbol, **kwargs):
        return self.data_map.get(symbol, pd.DataFrame())

def load_strategy(filepath):
    module_name = os.path.basename(filepath).replace('.py', '')
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

STRATEGIES = [
    {"name": "ML_Momentum_v1", "path": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py"},
    {"name": "ML_Momentum_v2", "path": "openalgo/strategies/scripts/advanced_ml_momentum_strategy_v2.py"},
    {"name": "AI_Hybrid_v1", "path": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py"},
    {"name": "AI_Hybrid_v2", "path": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout_v2.py"},
    {"name": "MCX_Momentum_v1", "path": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py"},
    {"name": "MCX_Momentum_v2", "path": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy_v2.py"},
]

def run_tests():
    regimes = ['TREND', 'RANGE']
    results = []

    # Generate Data
    data_map = {}
    for r in regimes:
        logger.info(f"Generating {r} data...")
        data_map[r] = generate_synthetic_data(regime=r)

    engine = SimpleBacktestEngine(initial_capital=100000)

    # 1. Baseline & V2 Comparison
    print("\n" + "="*80)
    print(f"{'STRATEGY':<25} | {'REGIME':<10} | {'RET %':<8} | {'SHARPE':<8} | {'DD %':<8} | {'TRADES':<6}")
    print("-" * 80)

    for strat_info in STRATEGIES:
        mod = load_strategy(strat_info['path'])

        for regime in regimes:
            # Inject Mock Client with data
            # The engine calls load_historical_data -> client.history
            # We need to Monkey Patch engine.load_historical_data OR client.
            # SimpleBacktestEngine creates client in __init__.
            # We can replace engine.client with MockClient.

            mock_client = MockClient({strat_info['name']: data_map[regime]})
            engine.client = mock_client

            # Monkey Patch load_historical_data to skip API call and return dataframe directly?
            # Or just rely on MockClient.history which is what engine calls.
            # Engine calls: self.client.history(...)

            # Run Backtest
            try:
                # We pass strat_info['name'] as symbol so MockClient returns the right data
                res = engine.run_backtest(
                    strategy_module=mod,
                    symbol=strat_info['name'],
                    exchange="MOCK",
                    start_date="2024-01-01",
                    end_date="2024-03-01",
                    interval="15m"
                )

                m = res['metrics']
                print(f"{strat_info['name']:<25} | {regime:<10} | {m['total_return_pct']:<8.2f} | {m['sharpe_ratio']:<8.2f} | {m['max_drawdown_pct']:<8.2f} | {res['total_trades']:<6}")

                results.append({
                    "strategy": strat_info['name'],
                    "regime": regime,
                    "return": m['total_return_pct'],
                    "sharpe": m['sharpe_ratio'],
                    "dd": m['max_drawdown_pct'],
                    "trades": res['total_trades']
                })
            except Exception as e:
                logger.error(f"Failed {strat_info['name']}: {e}")

    # 2. Parameter Tuning for V2
    print("\n" + "="*80)
    print("Parameter Tuning (Trend Regime)")
    print("-" * 80)

    tuning_grid = [
        {"name": "ML_Momentum_v2", "path": "openalgo/strategies/scripts/advanced_ml_momentum_strategy_v2.py",
         "params": [{"adx_threshold": 15}, {"adx_threshold": 25}, {"atr_trail_mult": 2.0}, {"atr_trail_mult": 4.0}]},

        {"name": "AI_Hybrid_v2", "path": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout_v2.py",
         "params": [{"adx_threshold_breakout": 20}, {"adx_threshold_breakout": 30}, {"rsi_upper": 65}]},

         {"name": "MCX_Momentum_v2", "path": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy_v2.py",
          "params": [{"min_atr": 5}, {"min_atr": 15}, {"adx_threshold": 30}]}
    ]

    for item in tuning_grid:
        mod = load_strategy(item['path'])
        base_name = item['name']

        # Use Trend Data for Tuning
        engine.client = MockClient({base_name: data_map['TREND']})

        for p in item['params']:
            # Create a wrapper to inject params
            original_gen = mod.generate_signal

            # Define wrapper inside loop to capture p
            def make_wrapper(param_dict):
                def wrapped(df, client=None, symbol=None):
                    return original_gen(df, client, symbol, params=param_dict)
                return wrapped

            # Monkey patch
            mod.generate_signal = make_wrapper(p)

            try:
                res = engine.run_backtest(mod, base_name, "MOCK", "2024-01-01", "2024-03-01")
                m = res['metrics']
                param_str = str(p)
                print(f"{base_name:<20} | Params: {param_str:<30} | Ret: {m['total_return_pct']:<6.2f} | Sharpe: {m['sharpe_ratio']:<6.2f}")
            except Exception as e:
                print(f"Error tuning {base_name}: {e}")

            # Restore
            mod.generate_signal = original_gen

if __name__ == "__main__":
    run_tests()
