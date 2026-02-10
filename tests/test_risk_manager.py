import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import sys
import json
from datetime import datetime, time as dt_time
import time

# Mock external dependencies before importing local modules
sys.modules['pandas'] = MagicMock()
sys.modules['kiteconnect'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['pytz'] = MagicMock()

# Add the project root to sys.path to ensure imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.utils.risk_manager import RiskManager, EODSquareOff

class TestRiskManager(unittest.TestCase):

    def setUp(self):
        # Patch the state file path in the module to avoid writing to the real file system
        self.patcher_path = patch('openalgo.strategies.utils.risk_manager.Path')
        self.MockPath = self.patcher_path.start()

        # Setup a mock state file
        self.mock_state_path = MagicMock()
        self.MockPath.return_value.resolve.return_value.parent.parent.__truediv__.return_value = self.mock_state_path
        self.mock_state_file = MagicMock()
        self.mock_state_path.__truediv__.return_value = self.mock_state_file
        # Ensure exists() returns True by default so _load_state tries to open it
        self.mock_state_file.exists.return_value = True

        # Mock datetime to control "now"
        self.patcher_datetime = patch('openalgo.strategies.utils.risk_manager.datetime')
        self.mock_datetime = self.patcher_datetime.start()
        self.mock_datetime.now.return_value = datetime(2023, 10, 27, 10, 0, 0) # Trading hours
        self.mock_datetime.strftime.return_value = '2023-10-27'

        # Mock time for cooldown checks
        self.patcher_time = patch('time.time')
        self.mock_time = self.patcher_time.start()
        self.mock_time.return_value = 100000.0

        # Mock built-in open for file I/O
        self.patcher_open = patch('builtins.open', mock_open(read_data='{}'))
        self.mock_file_open = self.patcher_open.start()

        # Mock json load/dump
        self.patcher_json = patch('json.load')
        self.mock_json_load = self.patcher_json.start()
        self.mock_json_load.return_value = {} # Default empty state

        self.patcher_json_dump = patch('json.dump')
        self.mock_json_dump = self.patcher_json_dump.start()

    def tearDown(self):
        self.patcher_path.stop()
        self.patcher_datetime.stop()
        self.patcher_time.stop()
        self.patcher_open.stop()
        self.patcher_json.stop()
        self.patcher_json_dump.stop()

    def test_initialization(self):
        rm = RiskManager("TestStrategy", "NSE", 100000)
        self.assertEqual(rm.strategy_name, "TestStrategy")
        self.assertEqual(rm.capital, 100000)
        self.assertEqual(rm.exchange, "NSE")
        # Check default config
        self.assertEqual(rm.config['max_loss_per_trade_pct'], 2.0)

    def test_load_state_same_day(self):
        # Mock json to return state from "today"
        state_data = {
            'date': '2023-10-27', # Matches mock_datetime.now()
            'daily_pnl': 500.0,
            'daily_trades': 2,
            'positions': {'TEST': {'qty': 10}},
            'circuit_breaker': False
        }
        self.mock_json_load.return_value = state_data

        rm = RiskManager("TestStrategy", "NSE")

        self.assertEqual(rm.daily_pnl, 500.0)
        self.assertEqual(rm.daily_trades, 2)
        self.assertEqual(len(rm.positions), 1)

    def test_load_state_new_day(self):
        # Mock json to return state from "yesterday"
        state_data = {
            'date': '2023-10-26', # Different day
            'daily_pnl': 500.0,
            'daily_trades': 2,
            'positions': {'TEST': {'qty': 10}},
            'circuit_breaker': True
        }
        self.mock_json_load.return_value = state_data

        rm = RiskManager("TestStrategy", "NSE")

        self.assertEqual(rm.daily_pnl, 0.0) # Should be reset
        self.assertEqual(rm.daily_trades, 0) # Should be reset
        self.assertEqual(len(rm.positions), 1) # Positions carried over
        self.assertFalse(rm.is_circuit_breaker_active) # Circuit breaker reset (default False)

    def test_can_trade_circuit_breaker(self):
        rm = RiskManager("TestStrategy", "NSE", 100000)
        rm.is_circuit_breaker_active = True
        can_trade, reason = rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER ACTIVE", reason)

    def test_can_trade_daily_loss_limit(self):
        rm = RiskManager("TestStrategy", "NSE", 100000)
        # Max loss is 5% of 100000 = 5000.
        rm.daily_pnl = -5001.0

        can_trade, reason = rm.can_trade()
        self.assertFalse(can_trade)
        self.assertTrue(rm.is_circuit_breaker_active)
        self.assertIn("CIRCUIT BREAKER TRIGGERED", reason)

    def test_can_trade_cooldown(self):
        rm = RiskManager("TestStrategy", "NSE")
        rm.last_trade_time = 100000.0 # Same as current time
        # Config cooldown is 300s

        can_trade, reason = rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Trade cooldown active", reason)

        # Advance time past cooldown
        self.mock_time.return_value = 100000.0 + 301
        can_trade, reason = rm.can_trade()
        self.assertTrue(can_trade)

    def test_register_entry(self):
        rm = RiskManager("TestStrategy", "NSE")
        rm.register_entry("TEST", 10, 100.0, "LONG")

        self.assertIn("TEST", rm.positions)
        pos = rm.positions["TEST"]
        self.assertEqual(pos['qty'], 10)
        self.assertEqual(pos['entry_price'], 100.0)
        # Check auto-calculated stop loss (2% default)
        self.assertEqual(pos['stop_loss'], 98.0)

        self.assertEqual(rm.daily_trades, 1)

    def test_register_exit(self):
        rm = RiskManager("TestStrategy", "NSE")
        rm.positions["TEST"] = {
            'qty': 10,
            'entry_price': 100.0,
            'side': 'LONG'
        }

        pnl = rm.register_exit("TEST", 110.0) # 10 * (110 - 100) = 100 profit

        self.assertEqual(pnl, 100.0)
        self.assertEqual(rm.daily_pnl, 100.0)
        self.assertNotIn("TEST", rm.positions)

    def test_trailing_stop_long(self):
        rm = RiskManager("TestStrategy", "NSE")
        rm.positions["TEST"] = {
            'qty': 10,
            'entry_price': 100.0,
            'stop_loss': 98.0,
            'trailing_stop': 98.0,
            'side': 'LONG'
        }

        # Price moves up to 105. Trailing stop (1.5%) should be 105 * (1 - 0.015) = 103.425
        # 103.425 > 98.0, so it should update
        new_stop = rm.update_trailing_stop("TEST", 105.0)
        self.assertAlmostEqual(new_stop, 103.425)
        self.assertAlmostEqual(rm.positions["TEST"]['trailing_stop'], 103.425)

        # Price drops to 104. Trailing stop should NOT lower.
        new_stop = rm.update_trailing_stop("TEST", 104.0)
        self.assertAlmostEqual(new_stop, 103.425)

    def test_check_stop_loss(self):
        rm = RiskManager("TestStrategy", "NSE")
        rm.positions["TEST"] = {
            'qty': 10,
            'entry_price': 100.0,
            'stop_loss': 98.0,
            'trailing_stop': 98.0,
            'side': 'LONG'
        }

        # Price at 99 - safe
        hit, reason = rm.check_stop_loss("TEST", 99.0)
        self.assertFalse(hit)

        # Price at 98 - hit
        hit, reason = rm.check_stop_loss("TEST", 98.0)
        self.assertTrue(hit)
        self.assertIn("STOP LOSS HIT", reason)

    def test_eod_square_off(self):
        rm = RiskManager("TestStrategy", "NSE")
        mock_callback = MagicMock(return_value={'status': 'success'})
        eod = EODSquareOff(rm, mock_callback)

        # Mock time to be before close (15:15 default)
        # 15:00
        self.mock_datetime.now.return_value = datetime(2023, 10, 27, 15, 0, 0)
        # Also need to mock timezone aware for RiskManager logic if it uses pytz
        # The code does: now = datetime.now(ist). The mock returns a naive datetime or mocked one.
        # But wait, the code calls `datetime.now(ist)`.
        # If I mock `datetime.now`, it should accept an argument.

        # Let's adjust the mock behavior for `now` to handle timezone arg
        def mock_now(tz=None):
            # Return a time based on test scenario
            return self.mock_now_value

        self.mock_datetime.now.side_effect = mock_now
        self.mock_now_value = datetime(2023, 10, 27, 15, 0, 0) # 3:00 PM

        # Not time yet
        executed = eod.check_and_execute()
        self.assertFalse(executed)

        # Advance time to 15:15
        self.mock_now_value = datetime(2023, 10, 27, 15, 15, 0)

        # Add a position
        rm.positions["TEST"] = {'qty': 10, 'entry_price': 100, 'side': 'LONG'}

        executed = eod.check_and_execute()
        self.assertTrue(executed)
        mock_callback.assert_called_with("TEST", "SELL", 10)

        # Verify position closed in RM
        self.assertNotIn("TEST", rm.positions)

if __name__ == '__main__':
    unittest.main()
