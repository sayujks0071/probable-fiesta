import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add paths
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(repo_root)
sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
# Also add vendor path if needed
sys.path.append(os.path.join(repo_root, 'vendor'))

# Import Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Try importing from local path if package structure is different
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

# Strategies
# We import them as modules
try:
    from openalgo.strategies.scripts import supertrend_vwap_strategy
    from openalgo.strategies.scripts import mcx_commodity_momentum_strategy
    from openalgo.strategies.scripts import ai_hybrid_reversion_breakout
    from openalgo.strategies.scripts import advanced_ml_momentum_strategy
except ImportError:
    # Fallback to direct file loading if package import fails
    import importlib.util
    def load_module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    supertrend_vwap_strategy = load_module("supertrend_vwap_strategy", os.path.join(repo_root, "openalgo/strategies/scripts/supertrend_vwap_strategy.py"))
    mcx_commodity_momentum_strategy = load_module("mcx_commodity_momentum_strategy", os.path.join(repo_root, "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py"))
    ai_hybrid_reversion_breakout = load_module("ai_hybrid_reversion_breakout", os.path.join(repo_root, "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py"))
    advanced_ml_momentum_strategy = load_module("advanced_ml_momentum_strategy", os.path.join(repo_root, "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py"))

def generate_synthetic_data(regime='TREND', length=1000):
    date_rng = pd.date_range(start='2024-01-01', periods=length, freq='15min')
    df = pd.DataFrame(date_rng, columns=['datetime'])
    df.set_index('datetime', inplace=True)

    # Base Price
    price = 100.0
    prices = [price]

    volatility = 0.002

    np.random.seed(42) # Reproducible

    for i in range(1, length):
        if regime == 'TREND':
            # Upward trend
            drift = 0.002 # Increased drift for stronger trend signal
            noise = np.random.normal(0, volatility)
            change = drift + noise
        elif regime == 'RANGE':
            # Mean Reversion
            mean_price = 100.0
            drift = -0.05 * (prices[-1] - mean_price) / mean_price # Pull back to mean
            noise = np.random.normal(0, volatility)
            change = drift + noise
        else:
            change = np.random.normal(0, volatility)

        new_price = prices[-1] * (1 + change)
        prices.append(new_price)

    df['close'] = prices
    df['open'] = df['close'].shift(1) * (1 + np.random.normal(0, 0.0005))
    df.loc[df.index[0], 'open'] = df['close'].iloc[0]

    # Generate High/Low
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.abs(np.random.normal(0, 0.001)))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.abs(np.random.normal(0, 0.001)))

    # Volume
    df['volume'] = np.random.randint(100, 1000, size=length)

    return df

def run_test():
    engine = SimpleBacktestEngine(initial_capital=100000)

    strategies = [
        # ("SuperTrend_VWAP", supertrend_vwap_strategy),
        ("MCX_Momentum", mcx_commodity_momentum_strategy),
        ("AI_Hybrid", ai_hybrid_reversion_breakout),
        ("ML_Momentum", advanced_ml_momentum_strategy)
    ]

    regimes = ['TREND', 'RANGE']

    results = []

    for regime in regimes:
        print(f"\n--- Testing Regime: {regime} ---")
        df = generate_synthetic_data(regime=regime, length=500)

        for name, module in strategies:
            print(f"Running {name}...", end='', flush=True)
            start_t = datetime.now()
            try:
                # Some strategies need params injection if they are strict wrappers
                # The generate_signal in scripts usually accepts params=None

                res = engine.run_backtest(
                    strategy_module=module,
                    symbol="SYNTH",
                    exchange="TEST",
                    start_date="2024-01-01",
                    end_date="2024-02-01",
                    interval="15m",
                    df=df
                )

                metrics = res.get('metrics', {})
                results.append({
                    "Strategy": name,
                    "Regime": regime,
                    "Sharpe": metrics.get('sharpe_ratio', 0),
                    "Return": metrics.get('total_return_pct', 0),
                    "Trades": res.get('total_trades', 0),
                    "DD": metrics.get('max_drawdown_pct', 0)
                })
                print(f" Done ({metrics.get('sharpe_ratio', 0):.2f}) in {(datetime.now() - start_t).total_seconds():.2f}s")
            except Exception as e:
                print(f" Failed {name}: {e}")
                import traceback
                traceback.print_exc()

    # Print Table
    print("\n--- LEADERBOARD ---")
    results.sort(key=lambda x: (x['Regime'], x['Sharpe']), reverse=True)

    print(f"{'Strategy':<20} | {'Regime':<10} | {'Sharpe':<10} | {'Return %':<10} | {'Trades':<8} | {'DD %':<10}")
    print("-" * 80)
    for r in results:
        print(f"{r['Strategy']:<20} | {r['Regime']:<10} | {r['Sharpe']:<10.2f} | {r['Return']:<10.2f} | {r['Trades']:<8} | {r['DD']:<10.2f}")

if __name__ == "__main__":
    run_test()
