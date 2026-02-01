#!/usr/bin/env python3
import os
import sys
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import importlib.util
from typing import Dict, List, Any

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import Strategies
from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
from openalgo.strategies.utils.trading_utils import APIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyntheticBacktest")

class SyntheticDataGenerator:
    """Generates synthetic OHLCV data for backtesting."""

    @staticmethod
    def generate_ohlcv(symbol, start_date, end_date, interval="15m", regime="random"):
        """
        Generate synthetic OHLCV data.
        regimes: 'trending' (uptrend), 'ranging' (sideways), 'volatile', 'random'
        """
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # Determine number of periods
        # Simple approx for 15m intervals
        delta = end - start
        periods_per_day = 25 # 6.25 hours / 15m
        total_periods = delta.days * periods_per_day

        dates = pd.date_range(start=start, periods=total_periods, freq='15min')
        dates = [d for d in dates if d.hour >= 9 and d.hour <= 15] # Filter market hours

        n = len(dates)
        if n == 0: return pd.DataFrame()

        # Base Price
        price = 1000.0
        prices = [price]

        # Parameters based on regime
        mu = 0.0001 # Drift
        sigma = 0.01 # Volatility

        if regime == 'trending':
            mu = 0.0005 # Strong Up
            sigma = 0.005
        elif regime == 'ranging':
            mu = 0.0
            sigma = 0.005
        elif regime == 'volatile':
            mu = 0.0
            sigma = 0.02

        # Generate Walk
        for _ in range(n-1):
            shock = np.random.normal(mu, sigma)
            price *= (1 + shock)
            prices.append(price)

        close = np.array(prices)

        # Generate OHLC
        high = close * (1 + np.abs(np.random.normal(0, 0.002, n)))
        low = close * (1 - np.abs(np.random.normal(0, 0.002, n)))
        open_p = close * (1 + np.random.normal(0, 0.002, n)) # Close of prev usually, but simple random here

        # Ensure Logic
        high = np.maximum(high, np.maximum(open_p, close))
        low = np.minimum(low, np.minimum(open_p, close))

        volume = np.random.randint(1000, 100000, n)

        # Add volume spikes
        spike_indices = np.random.choice(n, int(n*0.05))
        volume[spike_indices] = volume[spike_indices] * 5

        df = pd.DataFrame({
            'datetime': dates,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
        df.set_index('datetime', inplace=True)

        return df

class MockAPIClient:
    """Mocks APIClient to return synthetic data."""
    def __init__(self, api_key=None, host=None):
        self.api_key = api_key or "mock_key"
        self.host = host or "mock_host"
        self.data_store = {}

    def history(self, symbol, exchange="NSE", interval="15m", start_date=None, end_date=None, **kwargs):
        # Generate on fly if not exists or return generic
        # Use a deterministic seed for reproducibility per symbol
        seed = abs(hash(symbol)) % (2**32)
        np.random.seed(seed)

        regime = "trending" if "TREND" in symbol else "random"
        if "RANGE" in symbol: regime = "ranging"
        if "VOL" in symbol: regime = "volatile"
        if symbol == "INDIA VIX":
             # Return VIX-like data (Mean 15, range 10-30)
             dates = pd.date_range(start=start_date, end=end_date, freq='D')
             n = len(dates)
             vix = 15 + np.random.normal(0, 2, n)
             vix = np.maximum(10, np.minimum(30, vix))
             return pd.DataFrame({'datetime': dates, 'close': vix, 'open': vix, 'high': vix+1, 'low': vix-1, 'volume': 1000})

        return SyntheticDataGenerator.generate_ohlcv(symbol, start_date, end_date, interval, regime)

    def get_quote(self, symbol, exchange="NSE", **kwargs):
        return {'ltp': 1000.0}

class SyntheticBacktestRunner:
    def __init__(self):
        self.results = []

    def run(self, strategies, start_date, end_date):
        # Patch SimpleBacktestEngine to use MockAPIClient
        # We can pass client instance if we modify engine, or patch the class usage.
        # SimpleBacktestEngine creates its own client in __init__.
        # We will subclass it to override __init__.

        class MockEngine(SimpleBacktestEngine):
            def __init__(self, initial_capital=100000.0):
                self.initial_capital = initial_capital
                self.current_capital = initial_capital
                self.client = MockAPIClient()
                self.positions = []
                self.closed_trades = []
                self.equity_curve = []
                self.metrics = {}

        engine = MockEngine(initial_capital=100000.0)

        for strat_config in strategies:
            logger.info(f"Testing {strat_config['name']} ({strat_config['regime']} Regime)...")

            # Load Module
            module_path = strat_config['file']
            spec = importlib.util.spec_from_file_location(strat_config['name'], os.path.join(repo_root, module_path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[strat_config['name']] = module
            spec.loader.exec_module(module)

            # Prepare Params Wrapper
            params = strat_config.get('params', {})
            original_gen = module.generate_signal

            # Helper to wrap signal generation with params
            def wrapped_gen(df, client=None, symbol=None):
                return original_gen(df, client, symbol, params=params)

            # Create Wrapper Module Object
            class ModuleWrapper:
                pass
            wrapper = ModuleWrapper()
            wrapper.generate_signal = wrapped_gen
            # Copy attributes
            for attr in dir(module):
                if not attr.startswith('__'):
                    setattr(wrapper, attr, getattr(module, attr))

            # Specific patches for strategies that need it
            if "MCX" in strat_config['name']:
                wrapper.TIME_STOP_BARS = 12

            # Run
            symbol_name = f"{strat_config['symbol']}_{strat_config['regime']}"
            res = engine.run_backtest(
                strategy_module=wrapper,
                symbol=symbol_name, # Symbol name triggers regime in MockAPI
                exchange="NSE",
                start_date=start_date,
                end_date=end_date,
                interval="15m"
            )

            if 'error' in res:
                logger.error(f"Failed: {res['error']}")
                continue

            metrics = res.get('metrics', {})
            self.results.append({
                "Strategy": strat_config['name'],
                "Regime": strat_config['regime'],
                "Return %": metrics.get('total_return_pct', 0),
                "Sharpe": metrics.get('sharpe_ratio', 0),
                "Drawdown %": metrics.get('max_drawdown_pct', 0),
                "Win Rate %": metrics.get('win_rate', 0),
                "Trades": metrics.get('total_trades', 0)
            })

    def save_leaderboard(self):
        df = pd.DataFrame(self.results)
        if df.empty:
            logger.warning("No results to save.")
            return

        # Sort
        df.sort_values(by=['Sharpe', 'Return %'], ascending=False, inplace=True)

        print("\n=== LEADERBOARD ===\n")
        print(df.to_markdown(index=False, floatfmt=".2f"))

        with open("BACKTEST_LEADERBOARD.md", "w") as f:
            f.write("# Synthetic Backtest Leaderboard\n\n")
            f.write(df.to_markdown(index=False, floatfmt=".2f"))

        # JSON
        df.to_json("BACKTEST_LEADERBOARD.json", orient='records', indent=4)

if __name__ == "__main__":
    runner = SyntheticBacktestRunner()

    # Define Strategies and Regimes to test
    # We test each strategy on 'trending' and 'ranging' to see regime sensitivity
    base_strategies = [
        {
            "name": "SuperTrend_VWAP",
            "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
            "symbol": "STK",
            "variants": [
                {"params": {}}, # Baseline
                {"params": {"threshold": 140}, "suffix": "v1_loose"},
                {"params": {"stop_pct": 2.5}, "suffix": "v2_wideSL"}
            ]
        },
        {
            "name": "MCX_Momentum",
            "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
            "symbol": "MCX",
            "variants": [
                {"params": {}},
                {"params": {"adx_threshold": 20}, "suffix": "v1_sens"},
                {"params": {"period_rsi": 10}, "suffix": "v2_fast"}
            ]
        },
        {
            "name": "AI_Hybrid",
            "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
            "symbol": "HYB",
            "variants": [
                {"params": {}},
                {"params": {"rsi_lower": 35, "rsi_upper": 65}, "suffix": "v1_easy"},
                {"params": {"stop_pct": 2.0}, "suffix": "v2_wideSL"}
            ]
        },
        {
            "name": "ML_Momentum",
            "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
            "symbol": "ML",
            "variants": [
                {"params": {}},
                {"params": {"threshold": 0.005}, "suffix": "v1_lowThresh"}
            ]
        }
    ]

    strategies = []
    regimes = ["trending", "ranging"]

    for strat in base_strategies:
        for regime in regimes:
            # Skip ML Momentum for ranging as it's purely trend following
            if strat['name'] == "ML_Momentum" and regime == "ranging": continue

            for variant in strat['variants']:
                name_suffix = variant.get('suffix', 'base')
                strategies.append({
                    "name": strat['name'] + "_" + name_suffix,
                    "file": strat['file'],
                    "symbol": strat['symbol'],
                    "regime": regime,
                    "params": variant['params'],
                    "orig_name": strat['name'] # For loading module
                })

    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    runner.run(strategies, start_date, end_date)
    runner.save_leaderboard()
