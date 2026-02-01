import unittest
import re
import sys
import os

# Add tools to path to import logic
sys.path.append(os.path.abspath('tools'))

from normalize_symbols_repo import normalize_mcx_symbol, MCX_PATTERN

class TestMCXStrictFormatting(unittest.TestCase):

    def normalize(self, text):
        return MCX_PATTERN.sub(normalize_mcx_symbol, text)

    def test_strict_gold_mini(self):
        # Target: GOLDM05FEB26FUT
        # Input variants
        self.assertEqual(self.normalize("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize("goldm5feb26fut"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")

    def test_strict_silver_mini(self):
        # Target: SILVERM27FEB26FUT
        self.assertEqual(self.normalize("SILVERM27FEB26FUT"), "SILVERM27FEB26FUT")
        self.assertEqual(self.normalize("silverm27feb26fut"), "SILVERM27FEB26FUT")

    def test_strict_crude_oil(self):
        # Target: CRUDEOIL19FEB26FUT
        self.assertEqual(self.normalize("CRUDEOIL19FEB26FUT"), "CRUDEOIL19FEB26FUT")
        self.assertEqual(self.normalize("crudeoil19feb26fut"), "CRUDEOIL19FEB26FUT")

    def test_padding_dd(self):
        # 5 -> 05
        self.assertEqual(self.normalize("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        # 05 -> 05
        self.assertEqual(self.normalize("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")

    def test_uppercase_mmm(self):
        self.assertEqual(self.normalize("GOLDM05feb26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize("GOLDM05Feb26FUT"), "GOLDM05FEB26FUT")

    def test_yy_preservation(self):
        # Should not change YY
        self.assertEqual(self.normalize("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize("GOLDM05FEB27FUT"), "GOLDM05FEB27FUT")

    def test_full_sentence_replacement(self):
        text = "Trade goldm5feb26fut and silverm27feb26fut today."
        expected = "Trade GOLDM05FEB26FUT and SILVERM27FEB26FUT today."
        self.assertEqual(self.normalize(text), expected)

if __name__ == '__main__':
    unittest.main()
