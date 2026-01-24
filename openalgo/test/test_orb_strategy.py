import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add paths
current_dir = os.path.dirname(os.path.abspath(__file__))
# root is ../../ from test/
root_dir = os.path.abspath(os.path.join(current_dir, '../'))
sys.path.insert(0, root_dir)

# Import strategy
# Since we added root_dir to path, we can import openalgo.strategies...
# But wait, openalgo folder is inside root_dir if root_dir is repo root.
# list_files(root) shows 'openalgo' folder.
# So if I add root_dir, I can do `from openalgo.strategies...`

# However, the strategy file imports `from utils.config`.
# It relies on sys.path hack inside the script.
# When importing here, that hack runs.

try:
    from openalgo.strategies.scripts.orb_strategy import ORBStrategy
except ImportError:
    # Try alternate path if test is run from openalgo/test
    sys.path.append(os.path.join(root_dir, 'strategies', 'scripts'))
    from orb_strategy import ORBStrategy

class TestORBStrategy(unittest.TestCase):
    def setUp(self):
        # Patch dependencies
        self.config_patcher = patch('openalgo.strategies.scripts.orb_strategy.StrategyConfig')
        self.MockConfig = self.config_patcher.start()

        self.api_patcher = patch('openalgo.strategies.scripts.orb_strategy.api')
        self.MockApi = self.api_patcher.start()

        # Setup Config Mock
        mock_config_instance = self.MockConfig.return_value
        mock_config_instance.api_key = "test_key"
        mock_config_instance.host = "http://test"
        mock_config_instance.get.return_value = None # defaults

        # Setup Strategy
        self.strategy = ORBStrategy(
            symbol="TEST",
            quantity=10,
            timeframe="1m",
            orb_minutes=15,
            stop_loss_pct=1.0,
            target_pct=2.0
        )
        self.strategy.client = self.MockApi.return_value

    def tearDown(self):
        self.config_patcher.stop()
        self.api_patcher.stop()

    def test_calculate_orb_success(self):
        # Mock start time to be in the past (e.g. 1 hour ago)
        now = datetime.now()
        past_start = now - timedelta(hours=1)
        self.strategy.get_market_start_time = MagicMock(return_value=past_start)

        # Create dummy history
        dates = pd.date_range(start=past_start, periods=20, freq='1min')
        df = pd.DataFrame({
            'time': dates,
            'open': [100.0] * 20,
            'high': [105.0] * 20,
            'low': [95.0] * 20,
            'close': [100.0] * 20,
            'volume': [1000] * 20
        })
        # Set one high and low specifically
        df.loc[5, 'high'] = 110.0
        df.loc[10, 'low'] = 90.0

        self.strategy.client.history.return_value = df

        result = self.strategy.calculate_orb()

        self.assertTrue(result)
        self.assertTrue(self.strategy.orb_calculated)
        self.assertEqual(self.strategy.orb_high, 110.0)
        self.assertEqual(self.strategy.orb_low, 90.0)

    def test_calculate_orb_too_early(self):
        # Mock start time to be very recent (e.g. 1 minute ago)
        # ORB period is 15 mins
        now = datetime.now()
        recent_start = now - timedelta(minutes=1)
        self.strategy.get_market_start_time = MagicMock(return_value=recent_start)

        result = self.strategy.calculate_orb()

        # Should return False because now < recent_start + 15m
        self.assertFalse(result)
        self.assertFalse(self.strategy.orb_calculated)

    def test_signal_generation_buy(self):
        self.strategy.orb_calculated = True
        self.strategy.orb_high = 100.0
        self.strategy.orb_low = 90.0
        self.strategy.position = None

        self.strategy.place_order("BUY", 101.0)

        self.assertEqual(self.strategy.position, "LONG")
        self.assertEqual(self.strategy.entry_price, 101.0)

    def test_monitor_position_exit_target(self):
        self.strategy.position = "LONG"
        self.strategy.entry_price = 100.0
        self.strategy.quantity = 10
        self.strategy.target_pct = 5.0 # Target 105

        # Patch sys.exit to avoid stopping test
        with patch('sys.exit') as mock_exit:
            self.strategy.monitor_position(106.0)
            mock_exit.assert_called_once_with(0)

        self.assertIsNone(self.strategy.position)

if __name__ == '__main__':
    unittest.main()
