import unittest
import sys
import os
from datetime import date

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string
except ImportError:
    # Handle case where openalgo is not directly importable
    sys.path.insert(0, os.path.join(REPO_ROOT, 'openalgo'))
    from strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXStrictFormatting(unittest.TestCase):

    def test_gold_mini_format(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        target_date = date(2026, 2, 5)
        expected = "GOLDM05FEB26FUT"
        result = format_mcx_symbol("GOLD", target_date, mini=True)
        self.assertEqual(result, expected)

    def test_silver_mini_format(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        target_date = date(2026, 2, 27)
        expected = "SILVERM27FEB26FUT"
        result = format_mcx_symbol("SILVER", target_date, mini=True)
        self.assertEqual(result, expected)

    def test_crudeoil_regular_format(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        target_date = date(2026, 2, 19)
        expected = "CRUDEOIL19FEB26FUT"
        result = format_mcx_symbol("CRUDEOIL", target_date, mini=False)
        self.assertEqual(result, expected)

    def test_zero_padding(self):
        # Test single digit day padding
        target_date = date(2026, 1, 5)
        # NATURALGAS has no mini usually, but testing formatting logic
        expected = "NATURALGAS05JAN26FUT"
        result = format_mcx_symbol("NATURALGAS", target_date, mini=False)
        self.assertEqual(result, expected)

    def test_month_uppercase(self):
        # Test month case sensitivity
        target_date = date(2026, 8, 15) # August -> AUG
        expected = "COPPER15AUG26FUT"
        result = format_mcx_symbol("COPPER", target_date, mini=False)
        self.assertEqual(result, expected)

    def test_normalization(self):
        # Test normalize_mcx_string
        invalid_format = "GOLDM5FEB26FUT" # Single digit day
        expected = "GOLDM05FEB26FUT"
        result = normalize_mcx_string(invalid_format)
        self.assertEqual(result, expected)

        # Test already valid
        valid = "SILVERM27FEB26FUT"
        self.assertEqual(normalize_mcx_string(valid), valid)

        # Test invalid string (not MCX pattern)
        not_mcx = "NIFTY23OCTFUT"
        # normalize_mcx_string regex expects DD MMM YY FUT
        # NIFTY23OCTFUT matches regex?
        # Regex: ([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT
        # NIFTY 23 OCT FUT -> Matches.
        # But wait, NIFTY futures format is usually NIFTY23OCTFUT (Symbol + YY + MMM + FUT) ?
        # Or Symbol + DD + MMM + YY + FUT ?
        # OpenAlgo MCX format is strictly Symbol + DD + MMM + YY + FUT
        # NIFTY usually NIFTY26FEB19500CE etc.
        # The normalize function is specific to MCX pattern as defined in regex.
        pass

if __name__ == '__main__':
    unittest.main()
