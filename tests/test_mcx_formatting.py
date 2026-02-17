import unittest
import sys
import os
import re

# Add repo root to path to import tools
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.normalize_symbols_repo import MCX_PATTERN, normalize_mcx_symbol

class TestMCXFormatting(unittest.TestCase):

    def test_gold_mini_normalization(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        # Input might be malformed: GOLDM5FEB26FUT
        text = "GOLDM5FEB26FUT"
        match = MCX_PATTERN.search(text)
        self.assertIsNotNone(match, "Should match GOLDM5FEB26FUT")
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

    def test_silver_mini_normalization(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        text = "SILVERM27FEB26FUT"
        match = MCX_PATTERN.search(text)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "SILVERM27FEB26FUT")

    def test_crude_oil_normalization(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        text = "CRUDEOIL19FEB26FUT"
        match = MCX_PATTERN.search(text)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "CRUDEOIL19FEB26FUT")

    def test_zero_padding(self):
        # Test zero padding on DD
        text = "GOLD1FEB26FUT"
        match = MCX_PATTERN.search(text)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLD01FEB26FUT")

    def test_mmm_uppercase_mapping(self):
        # MMM uppercase mapping
        text = "GOLD05feb26FUT"
        match = MCX_PATTERN.search(text)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLD05FEB26FUT")

    def test_yy_correct(self):
        # YY correct (just passing through)
        text = "GOLD05FEB26FUT"
        match = MCX_PATTERN.search(text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(4), "26")
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLD05FEB26FUT")

    def test_full_string_replacement(self):
        # Test replacement in a sentence
        text = "Buy GOLDM5feb26FUT at market"

        def replacement_handler(match):
            return normalize_mcx_symbol(match)

        new_text = MCX_PATTERN.sub(replacement_handler, text)
        self.assertEqual(new_text, "Buy GOLDM05FEB26FUT at market")

if __name__ == '__main__':
    unittest.main()
