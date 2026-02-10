#!/usr/bin/env python3
import os
import sys
import logging
import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import importlib

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
from openalgo.strategies.utils.trading_utils import APIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ImprovedBacktest")

class ImprovedBacktester:
    def __init__(self, days=60):
        self.days = days
        self.results = []

    def load_strategy_module(self, strategy_name):
        try:
            # Try specific paths
            paths = [
                f"openalgo.strategies.scripts.{strategy_name}",
                f"vendor.openalgo.strategies.scripts.{strategy_name}"
            ]
            for path in paths:
                try:
                    module = importlib.import_module(path)
                    return module
                except ImportError:
                    continue
            logger.error(f"Could not import strategy module: {strategy_name}")
            return None
        except Exception as e:
            logger.error(f"Error loading strategy {strategy_name}: {e}")
            return None

    def generate_trend_data(self, symbol, days=30):
        """Generate strong uptrend data."""
        dates = pd.date_range(end=datetime.now(), periods=days*75, freq='15min')
        price = 10000
        opens = []
        for _ in range(len(dates)):
            # Positive drift
            change = random.normalvariate(2, 5)
            price += change
            opens.append(price)

        df = pd.DataFrame({
            'datetime': dates,
            'open': opens,
            'volume': [random.randint(500, 2000) for _ in range(len(dates))]
        })
        # Add some volatility
        df['close'] = df['open'] + [random.normalvariate(0, 3) for _ in range(len(dates))]
        df['high'] = df[['open', 'close']].max(axis=1) + 5
        df['low'] = df[['open', 'close']].min(axis=1) - 5
        df['timestamp'] = df['datetime']
        df.set_index('datetime', inplace=True)
        return df

    def generate_range_data(self, symbol, days=30):
        """Generate choppy/ranging data (Mean Reverting)."""
        dates = pd.date_range(end=datetime.now(), periods=days*75, freq='15min')
        base_price = 10000
        opens = []
        for i in range(len(dates)):
            # Sine wave + noise
            price = base_price + (200 * np.sin(i / 50)) + random.normalvariate(0, 10)
            opens.append(price)

        df = pd.DataFrame({
            'datetime': dates,
            'open': opens,
            'volume': [random.randint(200, 1000) for _ in range(len(dates))]
        })
        df['close'] = df['open'] + [random.normalvariate(0, 5) for _ in range(len(dates))]
        df['high'] = df[['open', 'close']].max(axis=1) + 8
        df['low'] = df[['open', 'close']].min(axis=1) - 8
        df['timestamp'] = df['datetime']
        df.set_index('datetime', inplace=True)
        return df

    def run_strategy(self, name, module_name, params, regime='TREND'):
        logger.info(f"Testing {name} in {regime} Regime...")

        engine = SimpleBacktestEngine(initial_capital=100000)
        strategy_module = self.load_strategy_module(module_name)

        if not strategy_module:
            return

        # Inject Data
        if regime == 'TREND':
            mock_df = self.generate_trend_data("TEST", self.days)
        else:
            mock_df = self.generate_range_data("TEST", self.days)

        engine.client.history = lambda **kwargs: mock_df

        # Wrapper to pass params
        original_gen = strategy_module.generate_signal

        class ModuleWrapper:
            def generate_signal(self, df, client=None, symbol=None):
                return original_gen(df, client=client, symbol=symbol, params=params)
            def __getattr__(self, name):
                return getattr(strategy_module, name)

        wrapped_module = ModuleWrapper()

        # Proxy check_exit if exists
        if hasattr(strategy_module, 'check_exit'):
             wrapped_module.check_exit = strategy_module.check_exit

        res = engine.run_backtest(
            strategy_module=wrapped_module,
            symbol="TEST",
            exchange="NSE",
            start_date=(datetime.now() - timedelta(days=self.days)).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d"),
            interval="15m"
        )

        metrics = res.get('metrics', {})
        metrics['strategy'] = name
        metrics['regime'] = regime
        metrics['total_trades'] = res.get('total_trades', 0)
        self.results.append(metrics)

    def run(self):
        strategies = [
            {
                'name': 'AI_Hybrid_v2_Improved',
                'module': 'ai_hybrid_reversion_breakout',
                'params': {'adx_threshold': 25, 'risk_amount': 1000, 'rsi_lower': 35, 'rsi_upper': 65}
            },
            {
                'name': 'MCX_Momentum_Improved',
                'module': 'mcx_commodity_momentum_strategy',
                'params': {'adx_threshold': 25, 'min_atr': 10}
            },
            {
                'name': 'SuperTrend_VWAP_Improved',
                'module': 'supertrend_vwap_strategy',
                'params': {'adx_threshold': 20}
            }
        ]

        for strat in strategies:
            self.run_strategy(strat['name'], strat['module'], strat['params'], 'TREND')
            self.run_strategy(strat['name'], strat['module'], strat['params'], 'RANGE')

        self.print_report()

    def print_report(self):
        df = pd.DataFrame(self.results)
        cols = ['strategy', 'regime', 'total_return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'win_rate', 'total_trades']
        print("\n📊 IMPROVED BACKTEST LEADERBOARD")
        print(df[cols].sort_values(['regime', 'sharpe_ratio'], ascending=False).to_markdown(index=False, floatfmt=".2f"))

if __name__ == "__main__":
    tester = ImprovedBacktester(days=60)
    tester.run()
