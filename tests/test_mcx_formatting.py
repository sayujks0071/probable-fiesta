import unittest
import sys
import os
from datetime import date

# Add repo root to path to allow importing openalgo
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXFormatting(unittest.TestCase):

    def test_gold_mini_strict(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        expected = "GOLDM05FEB26FUT"
        expiry = date(2026, 2, 5)
        result = format_mcx_symbol("GOLD", expiry, mini=True)
        self.assertEqual(result, expected)

    def test_silver_mini_strict(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        expected = "SILVERM27FEB26FUT"
        expiry = date(2026, 2, 27)
        result = format_mcx_symbol("SILVER", expiry, mini=True)
        self.assertEqual(result, expected)

    def test_crudeoil_standard_strict(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        expected = "CRUDEOIL19FEB26FUT"
        expiry = date(2026, 2, 19)
        result = format_mcx_symbol("CRUDEOIL", expiry, mini=False)
        self.assertEqual(result, expected)

    def test_zero_padding_day(self):
        # Test single digit day padding
        # e.g., 5th -> 05
        expiry = date(2026, 2, 5)
        result = format_mcx_symbol("GOLD", expiry, mini=True)
        self.assertIn("05", result)
        self.assertEqual(result, "GOLDM05FEB26FUT")

    def test_month_uppercase(self):
        # Test month is uppercase
        expiry = date(2026, 2, 5) # FEB
        result = format_mcx_symbol("GOLD", expiry, mini=True)
        self.assertIn("FEB", result)

        # Test another month like DEC
        expiry = date(2026, 12, 1)
        result = format_mcx_symbol("GOLD", expiry, mini=True)
        self.assertIn("DEC", result)

    def test_year_format(self):
        # Test 2 digit year
        expiry = date(2026, 2, 5)
        result = format_mcx_symbol("GOLD", expiry, mini=True)
        self.assertIn("26FUT", result)

    def test_normalize_mcx_string(self):
        # Normalize malformed string
        malformed = "GOLDM5FEB26FUT" # Missing padding
        expected = "GOLDM05FEB26FUT"
        self.assertEqual(normalize_mcx_string(malformed), expected)

        # Already normal
        self.assertEqual(normalize_mcx_string(expected), expected)

        # Lowercase input
        lowercase = "goldm05feb26fut"
        self.assertEqual(normalize_mcx_string(lowercase), expected)

if __name__ == '__main__':
    unittest.main()
