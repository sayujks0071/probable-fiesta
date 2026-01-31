import unittest
import sys
import os
from datetime import date

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.utils.trading_utils import format_mcx_symbol

class TestMCXFormatting(unittest.TestCase):
    def test_strict_examples(self):
        """Test specific examples required by strict mode policy"""

        # Case 1: GOLD Mini
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        symbol = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True)
        self.assertEqual(symbol, "GOLDM05FEB26FUT")

        # Case 2: SILVER Mini
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        symbol = format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True)
        self.assertEqual(symbol, "SILVERM27FEB26FUT")

        # Case 3: CRUDEOIL Standard
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        symbol = format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False)
        self.assertEqual(symbol, "CRUDEOIL19FEB26FUT")

    def test_formatting_rules(self):
        """Test general formatting rules"""

        # Zero padding on DD (Day 1 -> 01)
        symbol = format_mcx_symbol("TEST", date(2026, 1, 1), mini=False)
        self.assertEqual(symbol, "TEST01JAN26FUT")

        # MMM uppercase mapping (aug -> AUG)
        symbol = format_mcx_symbol("TEST", date(2026, 8, 15), mini=False)
        self.assertIn("AUG", symbol)
        self.assertEqual(symbol, "TEST15AUG26FUT")

        # YY correct (2025 -> 25)
        symbol = format_mcx_symbol("TEST", date(2025, 12, 31), mini=False)
        self.assertTrue(symbol.endswith("25FUT"))
        self.assertEqual(symbol, "TEST31DEC25FUT")

    def test_mini_logic(self):
        """Test mini logic details"""
        # If base already has M? Logic assumes base is raw commodity.
        # But if user passes GOLDM and mini=True?
        # Current implementation appends M. So GOLDMM.
        # This is expected behavior for the function as implemented ("Heuristic: Append M").
        # If user passes GOLDM and mini=False?
        symbol = format_mcx_symbol("GOLDM", date(2026, 2, 5), mini=False)
        self.assertEqual(symbol, "GOLDM05FEB26FUT")

if __name__ == '__main__':
    unittest.main()
