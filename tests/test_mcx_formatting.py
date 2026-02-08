import unittest
from datetime import date
import sys
import os

# Add repo root to path to import openalgo
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol

class TestMCXFormatting(unittest.TestCase):
    def test_strict_mcx_formats(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        # Underlying: GOLD
        self.assertEqual(
            format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True),
            "GOLDM05FEB26FUT"
        )

        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        # Underlying: SILVER
        self.assertEqual(
            format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True),
            "SILVERM27FEB26FUT"
        )

        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        # Underlying: CRUDEOIL
        self.assertEqual(
            format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False),
            "CRUDEOIL19FEB26FUT"
        )

    def test_zero_padding(self):
        # Test single digit day padding
        # date(2026, 1, 1) -> 01
        self.assertEqual(
            format_mcx_symbol("TEST", date(2026, 1, 1), mini=False),
            "TEST01JAN26FUT"
        )

    def test_mmm_uppercase(self):
        # Test month case (should be uppercase)
        # date(2026, 5, 10) -> MAY (not May)
        self.assertEqual(
            format_mcx_symbol("TEST", date(2026, 5, 10), mini=False),
            "TEST10MAY26FUT"
        )

    def test_yy_correct(self):
        # Test year format (YY)
        # date(2025, 12, 31) -> 25
        self.assertEqual(
            format_mcx_symbol("TEST", date(2025, 12, 31), mini=False),
            "TEST31DEC25FUT"
        )

if __name__ == '__main__':
    unittest.main()
