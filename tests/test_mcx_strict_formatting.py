import unittest
from datetime import date
import sys
import os

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if os.path.join(REPO_ROOT, 'openalgo') not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, 'openalgo'))

try:
    from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string
except ImportError:
    # Fallback for when running from root
    try:
        from strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string
    except ImportError:
         # Fallback assuming we are in REPO_ROOT and openalgo is a package
         from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXStrictFormatting(unittest.TestCase):
    def test_gold_mini(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        symbol = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True)
        self.assertEqual(symbol, "GOLDM05FEB26FUT")

    def test_silver_mini(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        symbol = format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True)
        self.assertEqual(symbol, "SILVERM27FEB26FUT")

    def test_crudeoil_standard(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        symbol = format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False)
        self.assertEqual(symbol, "CRUDEOIL19FEB26FUT")

    def test_zero_padding_dd(self):
        symbol = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=False)
        self.assertEqual(symbol, "GOLD05FEB26FUT")

    def test_mmm_uppercase(self):
        symbol = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=False)
        self.assertIn("FEB", symbol)

    def test_yy_correct(self):
        symbol = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=False)
        self.assertTrue(symbol.endswith("26FUT"))

    def test_normalize_lowercase(self):
        # goldm05feb26fut -> GOLDM05FEB26FUT
        original = "goldm05feb26fut"
        normalized = normalize_mcx_string(original)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

    def test_normalize_single_digit(self):
        # GOLDM5FEB26FUT -> GOLDM05FEB26FUT
        original = "GOLDM5FEB26FUT"
        normalized = normalize_mcx_string(original)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

if __name__ == '__main__':
    unittest.main()
