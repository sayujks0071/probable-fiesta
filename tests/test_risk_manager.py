import unittest
import os
import json
import shutil
import time
from datetime import datetime, time as dt_time
from unittest.mock import MagicMock, patch
from pathlib import Path

# Adjust path to import the module if necessary, assuming openalgo is in python path
from openalgo.strategies.utils.risk_manager import RiskManager, EODSquareOff

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.strategy_name = "TestStrategy"
        self.exchange = "NSE"
        self.capital = 100000
        # Initialize RiskManager
        self.rm = RiskManager(self.strategy_name, self.exchange, self.capital)
        # Ensure state directory is clean or at least we know the file path
        self.state_file = self.rm.state_file

    def tearDown(self):
        # Clean up the state file
        if self.state_file.exists():
            os.remove(self.state_file)

        # Optionally remove the state directory if it's empty, but riskier if other tests run in parallel
        # For now, just removing the file is enough.

    def test_initialization(self):
        """Test default config and overrides."""
        self.assertEqual(self.rm.config['max_daily_loss_pct'], 5.0)
        self.assertEqual(self.rm.config['max_loss_per_trade_pct'], 2.0)

        # Test override
        config = {'max_daily_loss_pct': 10.0}
        rm2 = RiskManager("TestStrategy2", "MCX", 200000, config)
        self.assertEqual(rm2.config['max_daily_loss_pct'], 10.0)
        self.assertEqual(rm2.config['max_loss_per_trade_pct'], 2.0) # Default preserved

        # Cleanup rm2 state
        if rm2.state_file.exists():
            os.remove(rm2.state_file)

    def test_state_persistence(self):
        """Test saving and loading state."""
        self.rm.daily_pnl = -500.0
        self.rm.daily_trades = 5
        self.rm.register_entry("INFY", 10, 1500.0, "LONG")

        # Force save is done inside register_entry

        # Create new instance with same strategy name
        rm_new = RiskManager(self.strategy_name, self.exchange, self.capital)

        self.assertEqual(rm_new.daily_pnl, -500.0)
        # daily_trades was 5, then register_entry adds 1 -> 6
        self.assertEqual(rm_new.daily_trades, 6)
        self.assertIn("INFY", rm_new.positions)
        self.assertEqual(rm_new.positions["INFY"]["entry_price"], 1500.0)

    def test_circuit_breaker(self):
        """Test max daily loss limit."""
        max_loss = self.capital * (self.rm.config['max_daily_loss_pct'] / 100)

        # Simulate loss
        self.rm.daily_pnl = -(max_loss + 1)

        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER TRIGGERED", reason)
        self.assertTrue(self.rm.is_circuit_breaker_active)

        # Subsequent check should return "CIRCUIT BREAKER ACTIVE"
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER ACTIVE", reason)

    @patch('openalgo.strategies.utils.risk_manager.datetime')
    def test_eod_square_off_time(self, mock_datetime):
        """Test EOD time check."""
        # Mock timezone to return a specific time
        mock_now = MagicMock()
        mock_datetime.now.return_value = mock_now

        # 15:10 - Before cutoff (15:15)
        mock_now.time.return_value = dt_time(15, 10)
        self.assertFalse(self.rm._is_near_market_close())

        # 15:15 - At cutoff
        mock_now.time.return_value = dt_time(15, 15)
        self.assertTrue(self.rm._is_near_market_close())

        # 15:20 - After cutoff
        mock_now.time.return_value = dt_time(15, 20)
        self.assertTrue(self.rm._is_near_market_close())

        # Verify can_trade blocks trading
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Near market close", reason)

    @patch('time.time')
    def test_trade_cooldown(self, mock_time):
        """Test trade cooldown."""
        # Ensure not near market close
        self.rm._is_near_market_close = MagicMock(return_value=False)

        # Mock time.time()
        start_time = 10000.0
        mock_time.return_value = start_time

        # Register a trade
        self.rm.register_entry("TATASTEEL", 100, 100.0, "LONG")
        self.assertEqual(self.rm.last_trade_time, start_time)

        # Try to trade immediately
        mock_time.return_value = start_time + 10 # 10s later
        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("Trade cooldown active", reason)

        # Try to trade after cooldown (300s default)
        mock_time.return_value = start_time + 301
        can_trade, reason = self.rm.can_trade()
        self.assertTrue(can_trade)

    def test_stop_loss_calculation(self):
        """Test SL calculation for Long and Short."""
        entry_price = 100.0
        pct = 2.0

        # Long
        sl_long = self.rm.calculate_stop_loss(entry_price, "LONG", pct)
        self.assertEqual(sl_long, 98.0)

        # Short
        sl_short = self.rm.calculate_stop_loss(entry_price, "SHORT", pct)
        self.assertEqual(sl_short, 102.0)

    def test_trailing_stop_update(self):
        """Test trailing stop updates."""
        entry_price = 100.0
        self.rm.register_entry("LONG_POS", 10, entry_price, "LONG")
        # Initial SL @ 98 (2% default)
        # Trailing pct is 1.5% default

        # Price goes up to 105
        # New trailing stop should be 105 * (1 - 0.015) = 103.425
        new_sl = self.rm.update_trailing_stop("LONG_POS", 105.0)
        self.assertAlmostEqual(new_sl, 103.425)
        self.assertAlmostEqual(self.rm.positions["LONG_POS"]["trailing_stop"], 103.425)

        # Price goes down to 104
        # SL should not move down
        new_sl = self.rm.update_trailing_stop("LONG_POS", 104.0)
        self.assertAlmostEqual(new_sl, 103.425) # Unchanged

        # Short Position
        self.rm.register_entry("SHORT_POS", 10, entry_price, "SHORT")
        # Initial SL @ 102

        # Price goes down to 95
        # New trailing stop should be 95 * (1 + 0.015) = 96.425
        new_sl = self.rm.update_trailing_stop("SHORT_POS", 95.0)
        self.assertAlmostEqual(new_sl, 96.425)

        # Price goes up to 96
        # SL should not move up
        new_sl = self.rm.update_trailing_stop("SHORT_POS", 96.0)
        self.assertAlmostEqual(new_sl, 96.425) # Unchanged

    def test_check_stop_loss(self):
        """Test stop loss hit detection."""
        # Long
        self.rm.register_entry("LONG_POS", 10, 100.0, "LONG")
        # SL @ 98

        hit, reason = self.rm.check_stop_loss("LONG_POS", 99.0)
        self.assertFalse(hit)

        hit, reason = self.rm.check_stop_loss("LONG_POS", 98.0)
        self.assertTrue(hit)
        self.assertIn("STOP LOSS HIT", reason)

        # Short
        self.rm.register_entry("SHORT_POS", 10, 100.0, "SHORT")
        # SL @ 102

        hit, reason = self.rm.check_stop_loss("SHORT_POS", 101.0)
        self.assertFalse(hit)

        hit, reason = self.rm.check_stop_loss("SHORT_POS", 102.5)
        self.assertTrue(hit)

    def test_pnl_calculation(self):
        """Test PnL updates on exit."""
        # Long Profit
        self.rm.register_entry("WINNER", 10, 100.0, "LONG")
        pnl = self.rm.register_exit("WINNER", 110.0)
        self.assertEqual(pnl, 100.0) # (110 - 100) * 10
        self.assertEqual(self.rm.daily_pnl, 100.0)
        self.assertNotIn("WINNER", self.rm.positions)

        # Short Loss
        self.rm.register_entry("LOSER", 10, 100.0, "SHORT")
        pnl = self.rm.register_exit("LOSER", 105.0)
        self.assertEqual(pnl, -50.0) # (100 - 105) * 10
        self.assertEqual(self.rm.daily_pnl, 50.0) # 100 - 50

class TestEODSquareOff(unittest.TestCase):
    def setUp(self):
        self.rm_mock = MagicMock()
        self.exit_callback = MagicMock()
        self.eod = EODSquareOff(self.rm_mock, self.exit_callback)

    def test_check_and_execute_no_action(self):
        """Should do nothing if not time or no positions."""
        self.rm_mock.should_square_off_eod.return_value = False
        self.assertFalse(self.eod.check_and_execute())

        self.rm_mock.should_square_off_eod.return_value = True
        self.rm_mock.get_open_positions.return_value = {}
        self.assertFalse(self.eod.check_and_execute())

    def test_check_and_execute_with_positions(self):
        """Should close positions."""
        self.rm_mock.should_square_off_eod.return_value = True
        self.rm_mock.get_open_positions.return_value = {
            "A": {"qty": 10, "entry_price": 100}, # Long
            "B": {"qty": -5, "entry_price": 200}  # Short
        }
        self.exit_callback.return_value = {'status': 'success'}

        executed = self.eod.check_and_execute()
        self.assertTrue(executed)

        # Check callbacks
        # A (Long 10) -> Should SELL 10
        self.exit_callback.assert_any_call("A", "SELL", 10)
        # B (Short 5) -> Should BUY 5
        self.exit_callback.assert_any_call("B", "BUY", 5)

        # Verify rm updates
        self.assertEqual(self.rm_mock.register_exit.call_count, 2)

        # Verify runs once
        self.assertFalse(self.eod.check_and_execute())

if __name__ == '__main__':
    unittest.main()
