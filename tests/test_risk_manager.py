
import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
from datetime import datetime, time as dt_time, timedelta
import json
from pathlib import Path
import importlib

# Adjust path to find openalgo
sys.path.append(os.getcwd())

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        # Patch modules before importing RiskManager
        self.modules_patcher = patch.dict(sys.modules, {
            'pandas': MagicMock(),
            'numpy': MagicMock(),
            'kiteconnect': MagicMock(),
            'pytz': MagicMock(),
            'pydantic': MagicMock()
        })
        self.modules_patcher.start()

        # Setup pytz mock to return UTC timezone
        from datetime import timezone
        sys.modules['pytz'].timezone.return_value = timezone.utc

        # Import the module under test
        # We need to use importlib to ensure we get a fresh import or at least import it after patching
        # However, if it was already imported, patching sys.modules might not re-trigger checks inside it,
        # but here we are mocking dependencies that are imported at top level of the module.
        # If the module was already imported, it would have failed or succeeded.
        # To be safe, we can try to reload if it exists, but for now standard import inside setUp is fine
        # assuming this test runs in a fresh process or before real imports.

        import openalgo.strategies.utils.risk_manager as rm_module
        # Force reload to ensure mocks are used if it was already loaded (e.g. by other tests)
        importlib.reload(rm_module)

        self.RiskManager = rm_module.RiskManager
        self.EODSquareOff = rm_module.EODSquareOff

        self.strategy_name = "TestStrategy"
        self.exchange = "NSE"
        self.capital = 100000

        # Patch Path to redirect state file to a temp location or mock
        self.mock_path_patcher = patch('openalgo.strategies.utils.risk_manager.Path')
        self.mock_path = self.mock_path_patcher.start()

        # Setup mock for state directory and file
        self.mock_state_dir = MagicMock()
        self.mock_state_file = MagicMock()
        self.mock_path.return_value.resolve.return_value.parent.parent.__truediv__.return_value = self.mock_state_dir
        self.mock_state_dir.__truediv__.return_value = self.mock_state_file
        self.mock_state_file.exists.return_value = False # Default no state file

        self.rm = self.RiskManager(self.strategy_name, self.exchange, self.capital)

    def tearDown(self):
        self.mock_path_patcher.stop()
        self.modules_patcher.stop()

    def test_initialization(self):
        self.assertEqual(self.rm.strategy_name, self.strategy_name)
        self.assertEqual(self.rm.exchange, self.exchange)
        self.assertEqual(self.rm.capital, self.capital)
        self.assertEqual(self.rm.daily_pnl, 0.0)
        self.assertEqual(self.rm.daily_trades, 0)
        self.assertFalse(self.rm.is_circuit_breaker_active)

    def test_can_trade_basic(self):
        can_trade, reason = self.rm.can_trade()
        self.assertTrue(can_trade)
        self.assertEqual(reason, "OK")

    def test_circuit_breaker_active(self):
        self.rm.is_circuit_breaker_active = True
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER ACTIVE", reason)

    def test_daily_loss_limit(self):
        # Max daily loss is 5% of 100,000 = 5,000
        self.rm.daily_pnl = -5001

        # Verify checking triggers circuit breaker
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertTrue(self.rm.is_circuit_breaker_active)
        self.assertIn("CIRCUIT BREAKER TRIGGERED", reason)

    @patch('openalgo.strategies.utils.risk_manager.datetime')
    def test_eod_square_off_time(self, mock_datetime):
        # Mock time to be near close (15:15 for NSE)
        # Set time to 15:15:00
        mock_now = datetime(2023, 1, 1, 15, 15, 0)
        mock_datetime.now.return_value = mock_now

        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Near market close", reason)

    @patch('time.time')
    def test_trade_cooldown(self, mock_time):
        mock_time.return_value = 1000
        self.rm.last_trade_time = 900 # 100 seconds ago
        # Default cooldown is 300s

        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Trade cooldown active", reason)

        mock_time.return_value = 1300 # 400 seconds ago
        can_trade, reason = self.rm.can_trade()
        self.assertTrue(can_trade)

    def test_calculate_stop_loss(self):
        # Long
        sl = self.rm.calculate_stop_loss(100, "LONG", 2.0)
        self.assertEqual(sl, 98.0)

        # Short
        sl = self.rm.calculate_stop_loss(100, "SHORT", 2.0)
        self.assertEqual(sl, 102.0)

    def test_update_trailing_stop_long(self):
        symbol = "TEST"
        self.rm.register_entry(symbol, 10, 100, "LONG")

        # Initial trailing stop should be stop loss (98.0 with default 2%)
        # Price moves up to 110. New trailing stop should be 110 * (1 - 1.5%) = 110 * 0.985 = 108.35
        new_stop = self.rm.update_trailing_stop(symbol, 110)
        self.assertAlmostEqual(new_stop, 108.35, places=2)
        self.assertAlmostEqual(self.rm.positions[symbol]['trailing_stop'], 108.35, places=2)

        # Price drops to 105. Trailing stop should NOT move down.
        new_stop = self.rm.update_trailing_stop(symbol, 105)
        self.assertAlmostEqual(new_stop, 108.35, places=2)

    def test_update_trailing_stop_short(self):
        symbol = "TEST"
        self.rm.register_entry(symbol, 10, 100, "SHORT")

        # Initial SL 102.0

        # Price moves down to 90. New trailing stop should be 90 * (1 + 1.5%) = 90 * 1.015 = 91.35
        new_stop = self.rm.update_trailing_stop(symbol, 90)
        self.assertAlmostEqual(new_stop, 91.35, places=2)

        # Price moves up to 95. Stop should NOT move up.
        new_stop = self.rm.update_trailing_stop(symbol, 95)
        self.assertAlmostEqual(new_stop, 91.35, places=2)

    def test_check_stop_loss(self):
        symbol = "TEST"
        self.rm.register_entry(symbol, 10, 100, "LONG")
        # SL 98.0

        hit, reason = self.rm.check_stop_loss(symbol, 99.0)
        self.assertFalse(hit)

        hit, reason = self.rm.check_stop_loss(symbol, 97.0)
        self.assertTrue(hit)
        self.assertIn("STOP LOSS HIT", reason)

    def test_register_exit(self):
        symbol = "TEST"
        self.rm.register_entry(symbol, 10, 100, "LONG")

        # Exit at 110. PnL = (110 - 100) * 10 = 100
        pnl = self.rm.register_exit(symbol, 110)
        self.assertEqual(pnl, 100.0)
        self.assertEqual(self.rm.daily_pnl, 100.0)
        self.assertNotIn(symbol, self.rm.positions)

    def test_eod_square_off(self):
        mock_callback = MagicMock(return_value={'status': 'success'})
        eod = self.EODSquareOff(self.rm, mock_callback)

        # Mock should_square_off_eod
        self.rm.should_square_off_eod = MagicMock(return_value=True)

        # Add a position
        self.rm.register_entry("TEST", 10, 100, "LONG")

        triggered = eod.check_and_execute()
        self.assertTrue(triggered)
        mock_callback.assert_called_with("TEST", "SELL", 10)
        self.assertNotIn("TEST", self.rm.positions)

if __name__ == '__main__':
    unittest.main()
