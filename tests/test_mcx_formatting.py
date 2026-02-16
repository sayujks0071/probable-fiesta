import unittest
from datetime import date
import re
import sys
import os

# Add repo root to path to import tools
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Import from tools
try:
    from tools.normalize_symbols_repo import MCX_PATTERN, normalize_mcx_symbol
except ImportError:
    # If run from within tools/ or something, try direct import or handle path issues
    sys.path.append(os.path.join(REPO_ROOT, 'tools'))
    from normalize_symbols_repo import MCX_PATTERN, normalize_mcx_symbol

class TestMCXFormatting(unittest.TestCase):

    def normalize_helper(self, symbol_str):
        # Emulate what re.sub does
        match = MCX_PATTERN.match(symbol_str)
        if not match:
            return symbol_str
        return normalize_mcx_symbol(match)

    def test_strict_mcx_formats(self):
        # 1. GOLDM05FEB26FUT
        self.assertEqual(self.normalize_helper("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize_helper("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")

        # 2. SILVERM27FEB26FUT
        self.assertEqual(self.normalize_helper("SILVERM27FEB26FUT"), "SILVERM27FEB26FUT")

        # 3. CRUDEOIL19FEB26FUT
        self.assertEqual(self.normalize_helper("CRUDEOIL19FEB26FUT"), "CRUDEOIL19FEB26FUT")

    def test_zero_padding_on_dd(self):
        self.assertEqual(self.normalize_helper("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize_helper("NATGAS9JAN24FUT"), "NATGAS09JAN24FUT")

    def test_mmm_uppercase_mapping(self):
        self.assertEqual(self.normalize_helper("GOLDM05feb26FUT"), "GOLDM05FEB26FUT")
        self.assertEqual(self.normalize_helper("GoldM05Feb26Fut"), "GOLDM05FEB26FUT")

    def test_yy_correct(self):
        self.assertEqual(self.normalize_helper("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")

    def test_non_matching(self):
        self.assertEqual(self.normalize_helper("INVALID"), "INVALID")

if __name__ == '__main__':
    unittest.main()
