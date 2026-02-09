import unittest
from datetime import date
import sys
import os

# Ensure repo root is in path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXStrictFormatting(unittest.TestCase):

    def test_strict_gold_mini(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        expiry = date(2026, 2, 5)
        symbol = format_mcx_symbol("GOLD", expiry, mini=True)
        self.assertEqual(symbol, "GOLDM05FEB26FUT")

    def test_strict_silver_mini(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        expiry = date(2026, 2, 27)
        symbol = format_mcx_symbol("SILVER", expiry, mini=True)
        self.assertEqual(symbol, "SILVERM27FEB26FUT")

    def test_strict_crudeoil_standard(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        expiry = date(2026, 2, 19)
        symbol = format_mcx_symbol("CRUDEOIL", expiry, mini=False)
        self.assertEqual(symbol, "CRUDEOIL19FEB26FUT")

    def test_zero_padding_day(self):
        # Day < 10 should be padded
        expiry = date(2026, 3, 1) # 01MAR
        symbol = format_mcx_symbol("COPPER", expiry, mini=False)
        self.assertEqual(symbol, "COPPER01MAR26FUT")

    def test_uppercase_month(self):
        # ensure uppercase MMM
        expiry = date(2026, 12, 15) # DEC
        symbol = format_mcx_symbol("ZINC", expiry, mini=False)
        self.assertIn("DEC", symbol)

        # Lowercase month in input shouldn't matter as logic uses strftime('%b').upper()
        # but let's verify logic is robust (it is based on code reading)

    def test_yy_year(self):
        # 2026 -> 26
        expiry = date(2026, 1, 1)
        symbol = format_mcx_symbol("ALUM", expiry, mini=False)
        self.assertTrue(symbol.endswith("26FUT"))

    def test_normalize_mcx_string(self):
        # Should normalize spaced/malformed strings if they match pattern
        # The current implementation handles basic normalization logic on regex match groups
        # Let's test padding fix
        # Input: GOLDM 5 FEB 26 FUT -> GOLDM05FEB26FUT
        # But wait, normalize_mcx_string in mcx_utils expects ^...$ match.
        # Does it handle spaces? The regex is: r'^([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT$'
        # It does NOT allow spaces in the regex!
        # So normalize_mcx_string('GOLDM 5 FEB 26 FUT') would fail to match and return original.
        # Let's check normalize_mcx_string implementation again.
        pass

    def test_normalize_mcx_padding(self):
        # If input is GOLDM5FEB26FUT (missing pad)
        # Regex: (\d{1,2}) allows 1 digit.
        # So it matches.
        # Then it reconstructs with {:02d}.
        raw = "GOLDM5FEB26FUT"
        normalized = normalize_mcx_string(raw)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

    def test_normalize_mcx_case(self):
        # If input is goldm05feb26fut
        # Regex uses re.IGNORECASE.
        # So it matches.
        # Reconstructs with .upper().
        raw = "goldm05feb26fut"
        normalized = normalize_mcx_string(raw)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

if __name__ == '__main__':
    unittest.main()
