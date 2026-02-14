import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from openalgo.strategies.scripts.mcx_commodity_momentum_strategy import MCXMomentumStrategy

class TestStrategyExecution(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_pm = MagicMock()
        self.mock_rm = MagicMock()

        # Setup strategy params
        self.params = {
            'period_adx': 14, 'period_rsi': 14, 'period_atr': 14,
            'adx_threshold': 25, 'min_atr': 0, 'risk_per_trade': 0.02,
            'seasonality_score': 60, 'global_alignment_score': 60,
            'usd_inr_volatility': 0.5
        }

        self.strategy = MCXMomentumStrategy("GOLDM05FEB26FUT", "key", "http://host", self.params)
        self.strategy.client = self.mock_client
        self.strategy.pm = self.mock_pm
        self.strategy.rm = self.mock_rm

        # Mock PositionManager state
        self.mock_pm.has_position.return_value = False
        self.mock_pm.position = 0

        # Mock RiskManager state
        self.mock_rm.can_trade.return_value = (True, "OK")

    def test_buy_signal_execution(self):
        # Create data that triggers BUY
        # Need 50+ rows
        dates = pd.date_range(start='2024-01-01', periods=60, freq='15min')
        df = pd.DataFrame(index=dates)
        df['open'] = 100.0
        df['high'] = 105.0
        df['low'] = 95.0
        df['close'] = 100.0
        df['volume'] = 1000

        # Initialize columns
        df['adx'] = 10.0
        df['rsi'] = 50.0
        df['atr'] = 10.0
        df['plus_dm'] = 0.0
        df['minus_dm'] = 0.0

        # Mock calculate_indicators to avoid overwriting our manual values
        self.strategy.calculate_indicators = MagicMock()

        # Set trigger values on completed candle (iloc[-2])
        # Need: Completed ADX > 25, Completed RSI > 55, Current Close > Completed Close

        idx_completed = -2
        idx_current = -1

        df.iloc[idx_completed, df.columns.get_loc('adx')] = 30.0 # > 25
        df.iloc[idx_completed, df.columns.get_loc('rsi')] = 60.0 # > 55
        df.iloc[idx_completed, df.columns.get_loc('close')] = 100.0

        # Set trigger values on current candle (iloc[-1])
        df.iloc[idx_current, df.columns.get_loc('close')] = 102.0 # > 100.0

        self.strategy.data = df
        self.strategy.check_signals()

        # Verify placesmartorder called
        self.mock_client.placesmartorder.assert_called_once()
        args, kwargs = self.mock_client.placesmartorder.call_args
        self.assertEqual(kwargs['action'], 'BUY')
        self.assertEqual(kwargs['symbol'], "GOLDM05FEB26FUT")
        self.assertEqual(kwargs['strategy'], "MCX_MOMENTUM")

    def test_sell_signal_execution(self):
        # Setup DF
        dates = pd.date_range(start='2024-01-01', periods=60, freq='15min')
        df = pd.DataFrame(index=dates)
        df['close'] = 100.0
        df['adx'] = 10.0
        df['rsi'] = 50.0
        df['atr'] = 10.0
        df['plus_dm'] = 0.0
        df['minus_dm'] = 0.0

        # Mock indicators
        self.strategy.calculate_indicators = MagicMock()

        # Set trigger values on completed candle (iloc[-2])
        idx_completed = -2
        idx_current = -1

        df.iloc[idx_completed, df.columns.get_loc('adx')] = 30.0 # > 25
        df.iloc[idx_completed, df.columns.get_loc('rsi')] = 40.0 # < 45
        df.iloc[idx_completed, df.columns.get_loc('close')] = 100.0

        # Set trigger values on current candle (iloc[-1])
        df.iloc[idx_current, df.columns.get_loc('close')] = 98.0 # < 100.0

        self.strategy.data = df
        self.strategy.check_signals()

        # Verify placesmartorder called
        self.mock_client.placesmartorder.assert_called_once()
        args, kwargs = self.mock_client.placesmartorder.call_args
        self.assertEqual(kwargs['action'], 'SELL')
        self.assertEqual(kwargs['strategy'], "MCX_MOMENTUM")

if __name__ == '__main__':
    unittest.main()
