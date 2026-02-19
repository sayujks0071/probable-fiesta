#!/usr/bin/env python3
"""
Synthetic Leaderboard Generator
Runs backtests on synthetic data to rank strategies across different market regimes.
"""
import os
import sys
import pandas as pd
import numpy as np
import logging
import json
import importlib.util
from datetime import datetime, timedelta

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyntheticLeaderboard")

# Add paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
STRATEGIES_DIR = os.path.join(PROJECT_ROOT, 'openalgo', 'strategies', 'scripts')
UTILS_DIR = os.path.join(PROJECT_ROOT, 'openalgo', 'strategies', 'utils')

sys.path.insert(0, UTILS_DIR)
sys.path.insert(0, PROJECT_ROOT)

# Import Backtest Engine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    sys.path.append(UTILS_DIR)
    from simple_backtest_engine import SimpleBacktestEngine

# -----------------------------------------------------------------------------
# Synthetic Data Generator
# -----------------------------------------------------------------------------
class SyntheticDataGenerator:
    @staticmethod
    def generate(regime='TREND', bars=1000, start_price=100.0, volatility=0.01):
        """
        Generate synthetic OHLCV data.
        Regimes: TREND (Up), DOWNTREND, RANGE, VOLATILE
        """
        np.random.seed(42) # Reproducible

        dates = pd.date_range(end=datetime.now(), periods=bars, freq='15min')
        prices = [start_price]
        volumes = []

        # Parameters
        drift = 0.0
        vol = volatility

        if regime == 'TREND':
            drift = 0.0005 # [Improvement] Stronger trend to trigger ADX > 20
            vol = 0.005
        elif regime == 'DOWNTREND':
            drift = -0.0005
            vol = 0.005
        elif regime == 'RANGE':
            drift = 0.0
            vol = 0.003
        elif regime == 'VOLATILE':
            drift = 0.0
            vol = 0.02

        # Generate Price Path
        for i in range(1, bars):
            prev = prices[-1]

            # Mean Reversion for Range
            if regime == 'RANGE':
                mean_rev = (start_price - prev) * 0.05
                change = np.random.normal(mean_rev, prev * vol)
            else:
                change = np.random.normal(prev * drift, prev * vol)

            prices.append(prev + change)

            # Volume (Higher on large moves)
            base_vol = 10000
            vol_spike = abs(change) / prev * 1000000
            volumes.append(int(base_vol + vol_spike + np.random.normal(0, 1000)))

        volumes.append(int(10000)) # Last volume

        # Create OHLC
        df = pd.DataFrame({'close': prices, 'volume': volumes}, index=dates)

        # Add Noise for H/L/O
        df['open'] = df['close'].shift(1).fillna(start_price) * (1 + np.random.normal(0, 0.001, bars))
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, vol/2, bars))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, vol/2, bars))

        # Ensure consistency
        df['high'] = df[['high', 'open', 'close']].max(axis=1)
        df['low'] = df[['low', 'open', 'close']].min(axis=1)

        # Add timestamp column for some strategies that expect it
        df['timestamp'] = df.index
        df['datetime'] = df.index

        return df

# -----------------------------------------------------------------------------
# Mock API Client
# -----------------------------------------------------------------------------
class MockAPIClient:
    def __init__(self, api_key=None, host=None):
        self.api_key = api_key
        self.host = host
        self.data_store = {} # Stores pre-generated data for symbols

    def history(self, symbol, interval, **kwargs):
        # Return synthetic data if available, else generate on fly
        if symbol in self.data_store:
            return self.data_store[symbol]

        # Default generation if not found
        # Extract regime from symbol name if possible (e.g. "TEST_TREND")
        regime = 'TREND'
        if 'RANGE' in symbol: regime = 'RANGE'
        elif 'DOWN' in symbol: regime = 'DOWNTREND'
        elif 'VOLATILE' in symbol: regime = 'VOLATILE'

        return SyntheticDataGenerator.generate(regime=regime)

    def placesmartorder(self, *args, **kwargs):
        pass # Mock

# -----------------------------------------------------------------------------
# Strategy Loader
# -----------------------------------------------------------------------------
STRATEGIES_TO_TEST = [
    {
        "name": "SuperTrend_VWAP",
        "file": "supertrend_vwap_strategy.py",
        "class_name": "SuperTrendVWAPStrategy"
    },
    {
        "name": "MCX_Momentum",
        "file": "mcx_commodity_momentum_strategy.py",
        "class_name": "MCXMomentumStrategy"
    },
    {
        "name": "AI_Hybrid",
        "file": "ai_hybrid_reversion_breakout.py",
        "class_name": "AIHybridStrategy"
    },
    {
        "name": "ML_Momentum",
        "file": "advanced_ml_momentum_strategy.py",
        "class_name": "MLMomentumStrategy"
    }
]

def load_strategy_module(filename):
    filepath = os.path.join(STRATEGIES_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[filename[:-3]] = module
    spec.loader.exec_module(module)
    return module

# -----------------------------------------------------------------------------
# Main Runner
# -----------------------------------------------------------------------------
def run_leaderboard():
    logger.info("Starting Synthetic Leaderboard...")

    regimes = ['TREND', 'RANGE', 'VOLATILE']
    results = []

    # 1. Prepare Data
    mock_client = MockAPIClient()
    for regime in regimes:
        symbol = f"SYNTH_{regime}"
        mock_client.data_store[symbol] = SyntheticDataGenerator.generate(regime=regime, bars=2000)

    # 2. Run Backtests
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    # Patch engine to use our mock client?
    # The strategies usually instantiate their own client.
    # We need to pass the client to the strategy or monkeypatch APIClient.

    # We will rely on the `generate_signal` wrapper approach used in SimpleBacktestEngine.
    # But wait, SimpleBacktestEngine calls `strategy_module.generate_signal(df, client=self.client, ...)`
    # So we just need to set `engine.client` to our mock client.
    engine.client = mock_client

    for strat_info in STRATEGIES_TO_TEST:
        logger.info(f"Testing {strat_info['name']}...")

        try:
            module = load_strategy_module(strat_info['file'])
        except Exception as e:
            logger.error(f"Failed to load {strat_info['name']}: {e}")
            continue

        if not hasattr(module, 'generate_signal'):
            logger.warning(f"{strat_info['name']} has no generate_signal function.")
            continue

        # Run for each regime
        for regime in regimes:
            symbol = f"SYNTH_{regime}"
            start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d") # Mock dates
            end_date = datetime.now().strftime("%Y-%m-%d")

            # The engine calls client.history inside run_backtest.
            # We need to ensure engine uses OUR mock client.
            # SimpleBacktestEngine.__init__ creates a client.
            # We can overwrite it.
            engine.client = mock_client

            # We also need to inject data into engine so it doesn't try to fetch again if we want control,
            # but MockAPIClient handles history() calls, so it's fine.

            try:
                # Capture result
                res = engine.run_backtest(
                    strategy_module=module,
                    symbol=symbol,
                    exchange="NSE", # Mock
                    start_date=start_date,
                    end_date=end_date,
                    interval="15m"
                )

                metrics = res.get('metrics', {})
                results.append({
                    "Strategy": strat_info['name'],
                    "Regime": regime,
                    "Return %": metrics.get('total_return_pct', 0),
                    "Sharpe": metrics.get('sharpe_ratio', 0),
                    "Drawdown %": metrics.get('max_drawdown_pct', 0),
                    "Win Rate %": metrics.get('win_rate', 0),
                    "Trades": res.get('total_trades', 0),
                    "Profit Factor": metrics.get('profit_factor', 0)
                })

            except Exception as e:
                logger.error(f"Error running {strat_info['name']} on {regime}: {e}", exc_info=True)

    # 3. Generate Report
    df_results = pd.DataFrame(results)
    if df_results.empty:
        logger.error("No results generated.")
        return

    # Calculate Weighted Score (Simple Average of Sharpe across Regimes)
    # Pivot to see performance per regime
    pivot = df_results.pivot(index='Strategy', columns='Regime', values=['Return %', 'Sharpe', 'Drawdown %'])

    # Save Raw Results
    output_dir = os.path.join(PROJECT_ROOT, 'openalgo', 'strategies', 'backtest_results')
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, 'synthetic_leaderboard.json')
    df_results.to_json(json_path, orient='records', indent=4)

    md_path = os.path.join(output_dir, 'synthetic_leaderboard.md')
    with open(md_path, 'w') as f:
        f.write("# Synthetic Strategy Leaderboard\n\n")
        f.write(f"Generated: {datetime.now()}\n\n")

        f.write("## Summary by Strategy (Average across Regimes)\n")
        summary = df_results.groupby('Strategy').agg({
            'Return %': 'mean',
            'Sharpe': 'mean',
            'Drawdown %': 'mean',
            'Trades': 'sum'
        }).sort_values('Sharpe', ascending=False)
        f.write(summary.to_markdown())
        f.write("\n\n")

        f.write("## Detailed Results by Regime\n")
        f.write(df_results.sort_values(['Regime', 'Sharpe'], ascending=[True, False]).to_markdown(index=False))

    logger.info(f"Leaderboard saved to {md_path}")
    print(df_results.to_markdown(index=False))

if __name__ == "__main__":
    run_leaderboard()
