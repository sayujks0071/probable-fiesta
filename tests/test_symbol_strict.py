import unittest
import sys
import os
import re

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.normalize_symbols_repo import normalize_mcx_symbol, MCX_PATTERN

class TestMCXNormalization(unittest.TestCase):
    def test_mcx_valid_symbols(self):
        # Test cases from requirements
        valid_cases = [
            ("GOLDM05FEB26FUT", "GOLDM05FEB26FUT"),
            ("SILVERM27FEB26FUT", "SILVERM27FEB26FUT"),
            ("CRUDEOIL19FEB26FUT", "CRUDEOIL19FEB26FUT"),
        ]

        for input_sym, expected in valid_cases:
            match = MCX_PATTERN.search(input_sym)
            self.assertIsNotNone(match, f"Failed to match valid symbol {input_sym}")
            normalized = normalize_mcx_symbol(match)
            self.assertEqual(normalized, expected)

    def test_mcx_normalization_needed(self):
        # Test padding
        input_sym = "GOLDM5FEB26FUT"
        expected = "GOLDM05FEB26FUT"

        match = MCX_PATTERN.search(input_sym)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, expected)

        # Test mixed case
        input_sym = "goldm05feb26fut"
        expected = "GOLDM05FEB26FUT"
        match = MCX_PATTERN.search(input_sym)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, expected)

    def test_mcx_invalid_month(self):
        # This logic is handled in the scanning loop in the script,
        # but the pattern itself matches 3 letters.
        # The script validates the month against a list.
        # Here we test that the pattern captures it correctly.
        input_sym = "GOLDM05XYZ26FUT"
        match = MCX_PATTERN.search(input_sym)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(3).upper(), "XYZ")

if __name__ == '__main__':
    unittest.main()
