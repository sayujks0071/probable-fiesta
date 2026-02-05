import unittest
import sys
import os
from datetime import date

# Ensure repo root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXFormatting(unittest.TestCase):
    def test_strict_examples(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        self.assertEqual(format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True), "GOLDM05FEB26FUT")

        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        self.assertEqual(format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True), "SILVERM27FEB26FUT")

        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        self.assertEqual(format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False), "CRUDEOIL19FEB26FUT")

    def test_zero_padding(self):
        # Day < 10 should be padded
        self.assertEqual(format_mcx_symbol("COPPER", date(2025, 5, 5), mini=False), "COPPER05MAY25FUT")
        self.assertEqual(format_mcx_symbol("COPPER", date(2025, 5, 15), mini=False), "COPPER15MAY25FUT")

    def test_mmm_uppercase(self):
        # Month should be uppercase
        self.assertIn("JAN", format_mcx_symbol("TEST", date(2025, 1, 1)))
        self.assertIn("DEC", format_mcx_symbol("TEST", date(2025, 12, 1)))

    def test_year_formatting(self):
        # Year should be 2 digits
        self.assertEqual(format_mcx_symbol("ZINC", date(2024, 1, 1)), "ZINC01JAN24FUT")

    def test_normalize_mcx_string(self):
        # Test normalization logic
        self.assertEqual(normalize_mcx_string("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(normalize_mcx_string("goldm05feb26fut"), "GOLDM05FEB26FUT")
        # Check invalid month returns original
        self.assertEqual(normalize_mcx_string("GOLDM05XXX26FUT"), "GOLDM05XXX26FUT")
        # Check invalid format returns original (based on current implementation regex match check)
        self.assertEqual(normalize_mcx_string("INVALID"), "INVALID")

if __name__ == '__main__':
    unittest.main()
