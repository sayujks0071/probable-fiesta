import sys
import os
import unittest
import re

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.normalize_symbols_repo import normalize_mcx_symbol, MCX_PATTERN

class TestMCXFormatting(unittest.TestCase):
    def normalize(self, symbol):
        match = MCX_PATTERN.search(symbol)
        if match:
            return normalize_mcx_symbol(match)
        return None

    def test_gold_mini_padding(self):
        # GOLDM 5 FEB 26 -> GOLDM05FEB26FUT
        # Note: The input string must match the regex fully to be captured.
        # "GOLDM5FEB26FUT" matches regex.
        self.assertEqual(self.normalize("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")

    def test_silver_mini_padding(self):
        # SILVERM 27 FEB 26 -> SILVERM27FEB26FUT
        self.assertEqual(self.normalize("SILVERM27FEB26FUT"), "SILVERM27FEB26FUT")

    def test_crude_oil_no_padding_needed(self):
        # CRUDEOIL 19 FEB 26 -> CRUDEOIL19FEB26FUT
        self.assertEqual(self.normalize("CRUDEOIL19FEB26FUT"), "CRUDEOIL19FEB26FUT")

    def test_crude_oil_padding_needed(self):
        # CRUDEOIL 5 FEB 26 -> CRUDEOIL05FEB26FUT
        self.assertEqual(self.normalize("CRUDEOIL5FEB26FUT"), "CRUDEOIL05FEB26FUT")

    def test_month_case_normalization(self):
        # goldm05feb26fut -> GOLDM05FEB26FUT
        # Regex is case insensitive
        self.assertEqual(self.normalize("goldm05feb26fut"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize("GOLDM05Feb26FUT"), "GOLDM05FEB26FUT")

    def test_symbol_case_normalization(self):
        self.assertEqual(self.normalize("goldm05FEB26FUT"), "GOLDM05FEB26FUT")

    def test_invalid_pattern(self):
        # Should not match regex
        self.assertIsNone(self.normalize("INVALID"))
        self.assertIsNone(self.normalize("GOLDFUT")) # Missing date

if __name__ == '__main__':
    unittest.main()
