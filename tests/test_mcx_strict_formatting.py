import unittest
from datetime import date
import sys
import os

# Ensure openalgo is in path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol

class TestMCXStrictFormatting(unittest.TestCase):
    def test_strict_requirements(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        # Assuming underlying is passed as base commodity name
        self.assertEqual(
            format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True),
            "GOLDM05FEB26FUT"
        )
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        self.assertEqual(
            format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True),
            "SILVERM27FEB26FUT"
        )
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        self.assertEqual(
            format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False),
            "CRUDEOIL19FEB26FUT"
        )

    def test_formatting_details(self):
        # Zero padding on DD
        self.assertEqual(
            format_mcx_symbol("COPPER", date(2026, 3, 5), mini=False),
            "COPPER05MAR26FUT"
        )
        # MMM uppercase mapping
        self.assertEqual(
            format_mcx_symbol("ZINC", date(2026, 4, 15), mini=False),
            "ZINC15APR26FUT"
        )
        # YY correct
        self.assertEqual(
            format_mcx_symbol("LEAD", date(2025, 12, 31), mini=False),
            "LEAD31DEC25FUT"
        )

if __name__ == '__main__':
    unittest.main()
