import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import sys
import os

# Add repo root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Import the strategy class
# We need to ensure the script can be imported.
# Since it is in strategies/scripts, we might need to add that to path or import via module path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

from openalgo.strategies.scripts.pairs_trading_mean_reversion import PairsTradingMeanReversion

class TestPairsTradingMeanReversion(unittest.TestCase):
    def setUp(self):
        self.symbol1 = "GOLDM05FEB26FUT"
        self.symbol2 = "SILVERM27FEB26FUT"
        self.api_key = "test_key"
        self.host = "http://test_host"

        # Patch dependencies
        self.patcher_api = patch('openalgo.strategies.scripts.pairs_trading_mean_reversion.APIClient')
        self.MockAPIClient = self.patcher_api.start()

        self.patcher_rm = patch('openalgo.strategies.scripts.pairs_trading_mean_reversion.RiskManager')
        self.MockRiskManager = self.patcher_rm.start()

        self.patcher_market = patch('openalgo.strategies.scripts.pairs_trading_mean_reversion.is_mcx_market_open')
        self.mock_is_market_open = self.patcher_market.start()
        self.mock_is_market_open.return_value = True

        self.strategy = PairsTradingMeanReversion(
            self.symbol1,
            self.symbol2,
            self.api_key,
            self.host,
            z_entry=0.1,  # Test Setting
            z_exit=0.05
        )

        # Mock client instance
        self.strategy.client = self.MockAPIClient.return_value
        self.strategy.rm = self.MockRiskManager.return_value
        self.strategy.rm.can_trade.return_value = (True, "OK")

    def tearDown(self):
        self.patcher_api.stop()
        self.patcher_rm.stop()
        self.patcher_market.stop()

    def create_synthetic_data(self, z_score_scenario):
        """
        Create synthetic data to produce desired Z-score.
        z_score_scenario: list of desired z-scores
        """
        # We need enough data for lookback (20)
        n = 30

        # Create base price series
        prices1 = np.ones(n) * 100
        prices2 = np.ones(n) * 50 # Ratio = 2.0

        # Create timestamps
        timestamps = pd.date_range(start='2024-01-01', periods=n, freq='15min')

        df1 = pd.DataFrame({'close': prices1, 'datetime': timestamps})
        df2 = pd.DataFrame({'close': prices2, 'datetime': timestamps})

        # Set index
        df1.set_index('datetime', inplace=True)
        df2.set_index('datetime', inplace=True)

        # Manually adjust the last few rows to create Z-score scenarios
        # This is tricky because z-score depends on rolling mean/std.
        # Instead, let's mock calculate_z_score return value directly
        # for precise control in tests, or just set dataframes and mock z-score calc.

        self.strategy.data1 = df1
        self.strategy.data2 = df2

        # Create aligned data
        aligned = df1[['close']].join(df2[['close']], lsuffix='_1', rsuffix='_2', how='inner')
        self.strategy.aligned_data = aligned

        return aligned

    def test_entry_short_spread(self):
        """Test entry when Z-Score > z_entry (0.1)"""
        # Mock calculate_z_score to return a dataframe with high z-score at iloc[-2]
        # We need a DataFrame with 'z_score', 'close_1', 'close_2'

        df = pd.DataFrame({
            'z_score': [0.0, 0.2, 0.0], # Middle value (iloc[-2]) is 0.2 > 0.1
            'close_1': [100, 105, 100],
            'close_2': [50, 50, 50]
        })

        with patch.object(self.strategy, 'calculate_z_score', return_value=df):
            self.strategy.check_signals()

            # Verify orders
            # Short Spread: Sell S1, Buy S2
            self.strategy.client.placesmartorder.assert_any_call(
                strategy="Pairs Trading Mean Reversion",
                symbol=self.symbol1,
                action="SELL",
                exchange="MCX",
                price_type="MARKET",
                product="MIS",
                quantity=1,
                position_size=1
            )

            self.strategy.client.placesmartorder.assert_any_call(
                strategy="Pairs Trading Mean Reversion",
                symbol=self.symbol2,
                action="BUY",
                exchange="MCX",
                price_type="MARKET",
                product="MIS",
                quantity=1,
                position_size=1
            )

            self.assertEqual(self.strategy.position, -1)
            self.strategy.rm.register_entry.assert_called()

    def test_entry_long_spread(self):
        """Test entry when Z-Score < -z_entry (-0.1)"""
        df = pd.DataFrame({
            'z_score': [0.0, -0.2, 0.0], # Middle value is -0.2 < -0.1
            'close_1': [95, 90, 95],
            'close_2': [50, 50, 50]
        })

        with patch.object(self.strategy, 'calculate_z_score', return_value=df):
            self.strategy.check_signals()

            # Long Spread: Buy S1, Sell S2
            self.strategy.client.placesmartorder.assert_any_call(
                strategy="Pairs Trading Mean Reversion",
                symbol=self.symbol1,
                action="BUY",
                exchange="MCX",
                price_type="MARKET",
                product="MIS",
                quantity=1,
                position_size=1
            )

            self.assertEqual(self.strategy.position, 1)

    def test_exit_short_spread(self):
        """Test exit when Short Spread and Z-Score < z_exit (0.05)"""
        self.strategy.position = -1 # Already Short

        df = pd.DataFrame({
            'z_score': [0.1, 0.04, 0.0], # 0.04 < 0.05
            'close_1': [100, 100, 100],
            'close_2': [50, 50, 50]
        })

        with patch.object(self.strategy, 'calculate_z_score', return_value=df):
            self.strategy.check_signals()

            # Exit Short Spread: Buy S1, Sell S2
            self.strategy.client.placesmartorder.assert_any_call(
                strategy="Pairs Trading Mean Reversion",
                symbol=self.symbol1,
                action="BUY",
                exchange="MCX",
                price_type="MARKET",
                product="MIS",
                quantity=1,
                position_size=1
            )

            self.assertEqual(self.strategy.position, 0)
            self.strategy.rm.register_exit.assert_called()

    def test_risk_manager_block(self):
        """Test that trades are blocked if Risk Manager returns False"""
        self.strategy.rm.can_trade.return_value = (False, "Blocked")

        df = pd.DataFrame({
            'z_score': [0.0, 0.2, 0.0],
            'close_1': [100, 105, 100],
            'close_2': [50, 50, 50]
        })

        with patch.object(self.strategy, 'calculate_z_score', return_value=df):
            self.strategy.check_signals()

            # Should NOT place orders
            self.strategy.client.placesmartorder.assert_not_called()
            self.assertEqual(self.strategy.position, 0)

if __name__ == '__main__':
    unittest.main()
