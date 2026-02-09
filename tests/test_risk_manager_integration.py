import unittest
import sys
import os
import shutil
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from openalgo.strategies.utils.risk_manager import RiskManager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.strategy_name = "TestStrategy"
        self.exchange = "NSE"
        self.capital = 100000
        self.rm = RiskManager(self.strategy_name, self.exchange, self.capital)

        # Clean up state file before test
        if self.rm.state_file.exists():
            self.rm.state_file.unlink()

        # Re-init to load clean state
        self.rm = RiskManager(self.strategy_name, self.exchange, self.capital)

    def tearDown(self):
        # Clean up state file after test
        if self.rm.state_file.exists():
            self.rm.state_file.unlink()

    def test_initialization(self):
        self.assertEqual(self.rm.daily_pnl, 0.0)
        self.assertEqual(self.rm.daily_trades, 0)
        self.assertEqual(len(self.rm.positions), 0)

    def test_register_entry(self):
        symbol = "TEST"
        qty = 10
        price = 100.0
        side = "LONG"

        self.rm.register_entry(symbol, qty, price, side)

        self.assertIn(symbol, self.rm.positions)
        self.assertEqual(self.rm.positions[symbol]['qty'], 10)
        self.assertEqual(self.rm.positions[symbol]['entry_price'], 100.0)
        # Check Default Stop Loss (2%)
        expected_sl = 98.0
        self.assertEqual(self.rm.positions[symbol]['stop_loss'], expected_sl)
        self.assertEqual(self.rm.daily_trades, 1)

    def test_stop_loss_hit(self):
        symbol = "TEST"
        self.rm.register_entry(symbol, 10, 100.0, "LONG")

        # Price drops to 99 (No SL)
        hit, reason = self.rm.check_stop_loss(symbol, 99.0)
        self.assertFalse(hit)

        # Price drops to 98 (SL Hit)
        hit, reason = self.rm.check_stop_loss(symbol, 98.0)
        self.assertTrue(hit)
        self.assertIn("STOP LOSS HIT", reason)

    def test_trailing_stop(self):
        symbol = "TEST"
        self.rm.register_entry(symbol, 10, 100.0, "LONG")

        # Initial Trailing Stop should be same as SL (98.0)
        self.assertEqual(self.rm.positions[symbol]['trailing_stop'], 98.0)

        # Price moves up to 105
        # Trailing pct is 1.5%. New stop = 105 * (1 - 0.015) = 105 * 0.985 = 103.425
        new_stop = self.rm.update_trailing_stop(symbol, 105.0)
        self.assertAlmostEqual(new_stop, 103.425)
        self.assertEqual(self.rm.positions[symbol]['trailing_stop'], new_stop)

        # Price drops to 104 (Above new stop)
        hit, reason = self.rm.check_stop_loss(symbol, 104.0)
        self.assertFalse(hit)

        # Price drops to 103 (Below new stop)
        hit, reason = self.rm.check_stop_loss(symbol, 103.0)
        self.assertTrue(hit)

    def test_circuit_breaker(self):
        # Max daily loss is 5% of 100000 = 5000

        # Simulate loss of 6000
        self.rm.daily_pnl = -6000.0

        can_trade, reason = self.rm.can_trade()
        self.assertFalse(can_trade)
        self.assertIn("CIRCUIT BREAKER TRIGGERED", reason)
        self.assertTrue(self.rm.is_circuit_breaker_active)

    def test_eod_check(self):
        # This is tricky because it relies on system time.
        # We can mock datetime in the module, but for now we just test the method exists.
        # Or we can override config time to be "now"
        pass

if __name__ == '__main__':
    unittest.main()
