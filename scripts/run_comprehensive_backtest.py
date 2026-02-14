import sys
import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(repo_root)

# Import Strategies
# We use importlib to handle imports robustly
import importlib.util

def load_module(filepath):
    module_name = os.path.basename(filepath).replace('.py', '')
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

STRATEGIES = {
    "SuperTrend_VWAP": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
    "MCX_Momentum": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
    "AI_Hybrid": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
    "ML_Momentum": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py"
}

# Import Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ComprehensiveBacktest")

class MockAPIClient:
    def __init__(self, data_map):
        self.data_map = data_map
        self.host = "MOCK"
        self.api_key = "MOCK"

    def history(self, symbol, exchange=None, interval="15m", start_date=None, end_date=None):
        # Return synthetic data for any symbol request to avoid network calls

        # Handle Special Symbols with realistic values
        if "VIX" in symbol.upper():
            # VIX around 15
            dates = pd.date_range(end=datetime.now(), periods=200, freq='15min')
            df = pd.DataFrame(index=dates)
            df['close'] = 15.0 + pd.Series(0.5 * np.random.randn(200)).values
            df['open'] = df['close']
            df['high'] = df['close'] + 0.1
            df['low'] = df['close'] - 0.1
            df['volume'] = 1000
            if 'datetime' not in df.columns: df['datetime'] = df.index
            return df

        if "NIFTY" in symbol.upper():
            # NIFTY around 22000
            dates = pd.date_range(end=datetime.now(), periods=200, freq='15min')
            df = pd.DataFrame(index=dates)
            # Uptrend
            t = np.linspace(0, 10, 200)
            price = 22000 + (t * 100) + np.random.normal(0, 50, 200)
            df['close'] = price
            df['open'] = price
            df['high'] = price + 20
            df['low'] = price - 20
            df['volume'] = 100000
            if 'datetime' not in df.columns: df['datetime'] = df.index
            return df

        # For main symbols, return TREND data as default or what is in map?
        # The engine uses `load_historical_data` for the main symbol.
        # This `history` method is called by strategies to fetch *other* data (like sector, VIX).
        # If they fetch the same symbol, we should probably return the same data?
        # But we don't know the current context here easily.
        # For 'Sector' or other stocks, return TREND data.
        if "TREND" in self.data_map:
            return self.data_map["TREND"].copy()
        return pd.DataFrame()

class OfflineBacktestEngine(SimpleBacktestEngine):
    def __init__(self, data_map):
        super().__init__(initial_capital=100000.0, api_key="test", host="test")
        self.data_map = data_map
        # Override client with Mock
        self.client = MockAPIClient(data_map)

    def load_historical_data(self, symbol, exchange, start_date, end_date, interval="15m"):
        if symbol in self.data_map:
            logger.info(f"Loading synthetic data for {symbol}")
            return self.data_map[symbol].copy()
        logger.warning(f"No synthetic data found for {symbol}")
        return pd.DataFrame()

def load_synthetic_data():
    data_dir = os.path.join(repo_root, 'openalgo', 'data', 'synthetic')
    datasets = {}
    for regime in ['trend', 'range', 'volatile']:
        filepath = os.path.join(data_dir, f"{regime}_data.csv")
        if os.path.exists(filepath):
            df = pd.read_csv(filepath)
            # Ensure datetime index
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df.set_index('datetime')
            elif 'timestamp' in df.columns:
                 df['timestamp'] = pd.to_datetime(df['timestamp'])
                 df = df.set_index('timestamp')

            datasets[regime.upper()] = df
    return datasets

def run_backtests(tuning_params=None):
    datasets = load_synthetic_data()
    if not datasets:
        logger.error("No synthetic data found. Run generate_synthetic_data.py first.")
        return

    engine = OfflineBacktestEngine(datasets)
    results = []

    for strat_name, strat_path in STRATEGIES.items():
        logger.info(f"Backtesting {strat_name}...")
        module = load_module(strat_path)

        # Check if we have variants (tuning)
        variants = [{'name': strat_name, 'params': {}}]
        if tuning_params and strat_name in tuning_params:
            import itertools
            grid = tuning_params[strat_name]
            keys = list(grid.keys())
            values = list(grid.values())
            combinations = list(itertools.product(*values))

            variants = []
            for i, combo in enumerate(combinations):
                p = dict(zip(keys, combo))
                variants.append({
                    'name': f"{strat_name}_v{i}",
                    'params': p
                })

        for variant in variants:
            # Create wrapper for params
            if not hasattr(module, 'generate_signal'):
                logger.error(f"{strat_name} missing generate_signal")
                continue

            # We need to wrap the generate_signal to inject params
            # The engine calls generate_signal(df, client, symbol)
            # Some modules have a wrapper that accepts params, some don't.
            # The wrapper I saw in daily_backtest_leaderboard used a partial.

            # Let's inspect the module's generate_signal signature or behavior?
            # Actually, the strategy files I read earlier all had a 'generate_signal' wrapper function at the end
            # that accepts (df, client=None, symbol=None, params=None).
            # So I can just bind params.

            original_gen = module.generate_signal

            class ModuleWrapper:
                pass

            wrapped_module = ModuleWrapper()

            # Helper to bind params
            def make_wrapper(gen_func, p):
                def wrapped(df, client=None, symbol=None):
                     # Call with params if the function supports it
                     # Looking at the code:
                     # SuperTrendVWAP: generate_signal(df, client=None, symbol=None, params=None)
                     # MCX: generate_signal(df, client=None, symbol=None, params=None)
                     # AIHybrid: generate_signal(df, client=None, symbol=None, params=None)
                     # MLMomentum: generate_signal(df, client=None, symbol=None, params=None)
                     # They all seem to support it now (I verified in read_file).
                     return gen_func(df, client, symbol, params=p)
                return wrapped

            wrapped_module.generate_signal = make_wrapper(original_gen, variant['params'])

            # Inject Constants/Defaults if needed by Engine check
            if hasattr(module, 'TIME_STOP_BARS'):
                wrapped_module.TIME_STOP_BARS = module.TIME_STOP_BARS

            # Inject Attributes that strategies might set
            # The strategy wrapper usually instantiates the class.

            regime_results = {}
            total_score = 0

            for regime_name in datasets.keys():
                logger.info(f"  > Regime: {regime_name}")

                # Run Backtest
                res = engine.run_backtest(
                    strategy_module=wrapped_module,
                    symbol=regime_name,
                    exchange="SYNTHETIC",
                    start_date="2024-01-01", # Dummy
                    end_date="2024-03-01",   # Dummy
                    interval="15m"
                )

                metrics = res.get('metrics', {})
                regime_results[regime_name] = metrics

                # Score: Sharpe Ratio
                sharpe = metrics.get('sharpe_ratio', 0)
                total_score += sharpe

            # Aggregate Results
            avg_sharpe = total_score / len(datasets)

            results.append({
                'strategy': variant['name'],
                'params': variant['params'],
                'avg_sharpe': avg_sharpe,
                'details': regime_results
            })

    # Sort
    results.sort(key=lambda x: x['avg_sharpe'], reverse=True)

    # Output
    print("\n=== LEADERBOARD ===")
    print(f"{'Rank':<5} {'Strategy':<25} {'Avg Sharpe':<10} {'Trend Sharpe':<12} {'Range Sharpe':<12} {'Volatile Sharpe':<12}")
    for i, res in enumerate(results):
        trend = res['details'].get('TREND', {}).get('sharpe_ratio', 0)
        rng = res['details'].get('RANGE', {}).get('sharpe_ratio', 0)
        vol = res['details'].get('VOLATILE', {}).get('sharpe_ratio', 0)
        print(f"{i+1:<5} {res['strategy']:<25} {res['avg_sharpe']:<10.2f} {trend:<12.2f} {rng:<12.2f} {vol:<12.2f}")

    output_file = "BACKTEST_RESULTS_TUNED.json" if tuning_params else "BACKTEST_RESULTS_BASELINE.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=4)
    print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--tune', action='store_true', help='Run with parameter tuning')
    args = parser.parse_args()

    tuning_grid = None
    if args.tune:
        tuning_grid = {
            "SuperTrend_VWAP": {
                "threshold": [150],
                "stop_pct": [1.5, 2.0]
            },
            "MCX_Momentum": {
                "adx_threshold": [20, 25],
                "period_rsi": [14]
            },
            "AI_Hybrid": {
                "rsi_lower": [30, 35],
                "rsi_upper": [60]
            },
            "ML_Momentum": {
                "threshold": [0.01],
                "vol_multiplier": [0.5, 1.0]
            }
        }

    run_backtests(tuning_grid)
