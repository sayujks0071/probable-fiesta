import unittest
import sys
import os
from datetime import date

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXFormatting(unittest.TestCase):
    def test_gold_mini_strict(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        expected = "GOLDM05FEB26FUT"
        actual = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True)
        self.assertEqual(actual, expected)

    def test_silver_mini_strict(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        expected = "SILVERM27FEB26FUT"
        actual = format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True)
        self.assertEqual(actual, expected)

    def test_crude_oil_strict(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        expected = "CRUDEOIL19FEB26FUT"
        actual = format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False)
        self.assertEqual(actual, expected)

    def test_normalization(self):
        # Test normalization logic
        # Pad Day
        self.assertEqual(normalize_mcx_string("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        # Already normalized
        self.assertEqual(normalize_mcx_string("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")
        # Case insensitivity (regex uses IGNORECASE but output should be upper)
        # Note: normalize_mcx_string expects symbol string matching regex.
        # It uses match.group(3).upper().
        self.assertEqual(normalize_mcx_string("goldm05feb26fut"), "GOLDM05FEB26FUT")

    def test_invalid_normalization(self):
        # Should return original if no match
        self.assertEqual(normalize_mcx_string("INVALID"), "INVALID")

if __name__ == '__main__':
    unittest.main()
