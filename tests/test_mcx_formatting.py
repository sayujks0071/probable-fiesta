import sys
import os
import unittest
import re

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, repo_root)

from tools.normalize_symbols_repo import normalize_mcx_symbol, MCX_PATTERN

class TestMCXFormatting(unittest.TestCase):
    def test_strict_gold_mini(self):
        # GOLDM05FEB26FUT for date(2026,2,5)
        raw = "GOLDM5FEB26FUT" # Test unpadded
        match = MCX_PATTERN.search(raw)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

        raw_correct = "GOLDM05FEB26FUT"
        match = MCX_PATTERN.search(raw_correct)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

    def test_strict_silver_mini(self):
        # SILVERM27FEB26FUT for date(2026,2,27)
        raw = "SILVERM27FEB26FUT"
        match = MCX_PATTERN.search(raw)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "SILVERM27FEB26FUT")

    def test_strict_crude_oil(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19)
        raw = "CRUDEOIL19FEB26FUT"
        match = MCX_PATTERN.search(raw)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "CRUDEOIL19FEB26FUT")

    def test_zero_padding(self):
        # Test day padding explicitly
        raw = "GOLDM1FEB26FUT"
        match = MCX_PATTERN.search(raw)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM01FEB26FUT")

    def test_case_mapping(self):
        # Test lower case to upper
        raw = "goldm05feb26fut"
        match = MCX_PATTERN.search(raw)
        self.assertIsNotNone(match)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM05FEB26FUT")

    def test_yy_correct(self):
        # Test year preservation
        raw = "GOLDM05FEB99FUT"
        match = MCX_PATTERN.search(raw)
        normalized = normalize_mcx_symbol(match)
        self.assertEqual(normalized, "GOLDM05FEB99FUT")

if __name__ == '__main__':
    unittest.main()
