import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# Adjust path to import strategy from scripts
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

try:
    from pairs_trading_mean_reversion import PairsTradingStrategy
except ImportError:
    sys.path.append(os.path.abspath('openalgo/strategies/scripts'))
    from pairs_trading_mean_reversion import PairsTradingStrategy

class TestPairsTradingStrategy(unittest.TestCase):
    def setUp(self):
        self.symbol1 = "GOLDM05FEB26FUT"
        self.symbol2 = "SILVERM27FEB26FUT"
        self.strategy = PairsTradingStrategy(
            self.symbol1, self.symbol2,
            api_key="test", host="http://test",
            z_entry=0.1, z_exit=0.05, lookback_period=5
        )

        # Mock Client and Risk Manager
        self.strategy.client = MagicMock()
        self.strategy.rm = MagicMock()
        self.strategy.rm.can_trade.return_value = (True, "OK")

    def test_calculate_z_score(self):
        data = pd.DataFrame({
            'close_1': [100, 101, 102, 103, 104, 105],
            'close_2': [50, 50, 50, 50, 50, 50]
        })

        df = self.strategy.calculate_z_score(data)
        z = df['z_score'].iloc[-1]

        self.assertIsNotNone(z)
        self.assertTrue(z > 1.0)

    def test_entry_signal_short_spread(self):
        """Test entry when Z > z_entry (0.1) -> Expect Sell 1, Buy 2"""
        df = pd.DataFrame({
            'ratio': [1.0]*20,
            'z_score': [0.0]*19 + [0.2] # 0.2 > 0.1
        })

        self.strategy.execute_trade = MagicMock(return_value=True)

        # Call the strategy method directly
        self.strategy.check_signals(df)

        # Assertions
        self.strategy.execute_trade.assert_called_with("SELL", "BUY")
        self.assertEqual(self.strategy.position, -1)

    def test_entry_signal_long_spread(self):
        """Test entry when Z < -z_entry (-0.1) -> Expect Buy 1, Sell 2"""
        df = pd.DataFrame({
            'ratio': [1.0]*20,
            'z_score': [0.0]*19 + [-0.2] # -0.2 < -0.1
        })

        self.strategy.execute_trade = MagicMock(return_value=True)

        self.strategy.check_signals(df)

        self.strategy.execute_trade.assert_called_with("BUY", "SELL")
        self.assertEqual(self.strategy.position, 1)

    def test_exit_signal(self):
        """Test exit when |Z| < z_exit (0.05)"""
        self.strategy.position = -1 # Short Spread

        df = pd.DataFrame({
            'ratio': [1.0]*20,
            'z_score': [0.0]*19 + [0.04] # 0.04 < 0.05
        })

        # Note: close_positions calls execute_trade
        self.strategy.execute_trade = MagicMock(return_value=True)

        self.strategy.check_signals(df)

        # Expect "BUY", "SELL" to close Short Spread
        self.strategy.execute_trade.assert_called_with("BUY", "SELL")
        self.assertEqual(self.strategy.position, 0)

if __name__ == '__main__':
    unittest.main()
