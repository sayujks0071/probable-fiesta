import unittest
import sys
import os
from datetime import date

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string, normalize_mcx_fuzzy

class TestMCXFormatting(unittest.TestCase):
    def test_format_mcx_symbol_strict(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        self.assertEqual(
            format_mcx_symbol('GOLD', date(2026, 2, 5), mini=True),
            'GOLDM05FEB26FUT'
        )
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        self.assertEqual(
            format_mcx_symbol('SILVER', date(2026, 2, 27), mini=True),
            'SILVERM27FEB26FUT'
        )
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        self.assertEqual(
            format_mcx_symbol('CRUDEOIL', date(2026, 2, 19), mini=False),
            'CRUDEOIL19FEB26FUT'
        )
        # Test zero padding
        self.assertEqual(
            format_mcx_symbol('COPPER', date(2025, 1, 1), mini=False),
            'COPPER01JAN25FUT'
        )

    def test_normalize_mcx_string_strict(self):
        # Already correct
        self.assertEqual(normalize_mcx_string("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")
        # Case insensitive
        self.assertEqual(normalize_mcx_string("goldm05feb26fut"), "GOLDM05FEB26FUT")

    def test_normalize_mcx_string_fuzzy(self):
        # Optional spaces
        self.assertEqual(normalize_mcx_string("GOLDM 05 FEB 26 FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(normalize_mcx_string("SILVERMIC 5 FEB 26 FUT"), "SILVERMIC05FEB26FUT")
        # Missing padding
        self.assertEqual(normalize_mcx_string("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        # Surrounding spaces
        self.assertEqual(normalize_mcx_string("  CRUDEOIL 19 FEB 26 FUT  "), "CRUDEOIL19FEB26FUT")

    def test_normalize_mcx_fuzzy_text_block(self):
        text = "Check GOLDM 5 FEB 26 FUT and SILVERMIC27FEB26FUT please."
        expected = "Check GOLDM05FEB26FUT and SILVERMIC27FEB26FUT please."
        self.assertEqual(normalize_mcx_fuzzy(text), expected)

    def test_invalid_strings(self):
        # Should remain unchanged
        self.assertEqual(normalize_mcx_string("NOT A SYMBOL"), "NOT A SYMBOL")
        # Invalid month format (digits instead of letters)
        self.assertEqual(normalize_mcx_string("GOLDM 05 123 26 FUT"), "GOLDM 05 123 26 FUT")

        # XYZ is valid pattern for [A-Z]{3} even if not a real month, so it gets normalized
        self.assertEqual(normalize_mcx_string("GOLDM 05 XYZ 26 FUT"), "GOLDM05XYZ26FUT")

if __name__ == '__main__':
    unittest.main()
