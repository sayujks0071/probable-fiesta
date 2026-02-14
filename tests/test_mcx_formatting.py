import unittest
import sys
import os
import re

# Add repo root to path to find tools
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TOOLS_DIR = os.path.join(REPO_ROOT, 'tools')

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

# Import from tools
from normalize_symbols_repo import normalize_mcx_symbol, MCX_PATTERN

class TestMCXFormatting(unittest.TestCase):
    def test_mcx_pattern_matching(self):
        """Test that the regex correctly identifies valid MCX symbols."""
        valid_symbols = [
            "GOLDM05FEB26FUT",
            "SILVERM27FEB26FUT",
            "CRUDEOIL19FEB26FUT",
            "GOLDM5FEB26FUT", # Needs normalization but matches pattern
            "goldm05feb26fut", # Needs normalization but matches pattern (case insensitive)
        ]
        for s in valid_symbols:
            match = MCX_PATTERN.search(s)
            self.assertIsNotNone(match, f"Failed to match valid symbol: {s}")

    def test_mcx_normalization_logic(self):
        """Test the normalization function logic."""
        test_cases = [
            ("GOLDM05FEB26FUT", "GOLDM05FEB26FUT"), # Already correct
            ("SILVERM27FEB26FUT", "SILVERM27FEB26FUT"), # Already correct
            ("CRUDEOIL19FEB26FUT", "CRUDEOIL19FEB26FUT"), # Already correct
            ("GOLDM5FEB26FUT", "GOLDM05FEB26FUT"), # Pad day
            ("goldm05feb26fut", "GOLDM05FEB26FUT"), # Uppercase
            ("crudeoil19feb26fut", "CRUDEOIL19FEB26FUT"), # Uppercase
        ]

        for original, expected in test_cases:
            match = MCX_PATTERN.search(original)
            self.assertIsNotNone(match, f"Failed to match: {original}")
            normalized = normalize_mcx_symbol(match)
            self.assertEqual(normalized, expected, f"Failed to normalize {original}")

    def test_invalid_month(self):
        """Test invalid month handling (logic check, not regex check as regex matches 3 letters)."""
        symbol = "GOLDM05XXX26FUT"
        match = MCX_PATTERN.search(symbol)
        self.assertIsNotNone(match)
        # normalize_mcx_symbol returns normalized string, validation happens in scan_file
        # But normalization should still work: XXX -> XXX
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM05XXX26FUT")

    def test_specific_date_requirements(self):
        """
        Verify specific date requirements mentioned in strict mode policy:
        - GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        - SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        - CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        """
        # These are just strings, but verify they are considered valid and normalized
        symbols = [
            "GOLDM05FEB26FUT",
            "SILVERM27FEB26FUT",
            "CRUDEOIL19FEB26FUT"
        ]
        for s in symbols:
            match = MCX_PATTERN.search(s)
            self.assertIsNotNone(match)
            normalized = normalize_mcx_symbol(match)
            self.assertEqual(normalized, s)

if __name__ == '__main__':
    unittest.main()
