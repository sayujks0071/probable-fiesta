
import unittest
import pandas as pd
import os
import shutil
import logging
from datetime import datetime, timedelta
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

# Mock Data
MOCK_CSV = "tests/mock_instruments.csv"

class TestSymbolResolverManual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a mock CSV
        data = [
            # MCX: SILVER vs SILVERMIC (MINI)
            {'exchange': 'MCX', 'symbol': 'SILVER26FEB', 'name': 'SILVER', 'expiry': '2026-02-28', 'lot_size': 30, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'SILVERMIC26FEB', 'name': 'SILVER', 'expiry': '2026-02-28', 'lot_size': 1, 'instrument_type': 'FUT'},

            # MCX: GOLD vs GOLDM (MINI)
            {'exchange': 'MCX', 'symbol': 'GOLD26FEB', 'name': 'GOLD', 'expiry': '2026-02-05', 'lot_size': 100, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'GOLDM26FEB', 'name': 'GOLD', 'expiry': '2026-02-05', 'lot_size': 10, 'instrument_type': 'FUT'},

            # NSE Options
            # Weekly: 5th Feb (Thu), 12th Feb (Thu)
            # Monthly: 26th Feb (Last Thu)
            {'exchange': 'NFO', 'symbol': 'NIFTY26FEB19000CE', 'name': 'NIFTY', 'expiry': '2026-02-05', 'instrument_type': 'OPT', 'lot_size': 50},
            {'exchange': 'NFO', 'symbol': 'NIFTY26FEB19500CE', 'name': 'NIFTY', 'expiry': '2026-02-12', 'instrument_type': 'OPT', 'lot_size': 50},
            {'exchange': 'NFO', 'symbol': 'NIFTY26FEB20000CE', 'name': 'NIFTY', 'expiry': '2026-02-26', 'instrument_type': 'OPT', 'lot_size': 50},
        ]
        pd.DataFrame(data).to_csv(MOCK_CSV, index=False)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(MOCK_CSV):
            os.remove(MOCK_CSV)

    def test_mcx_mini_preference(self):
        resolver = SymbolResolver(MOCK_CSV)

        # Test SILVER -> Should resolve to SILVERMIC (Lot 1)
        res = resolver.resolve({'underlying': 'SILVER', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVERMIC26FEB')

        # Test GOLD -> Should resolve to GOLDM (Lot 10)
        res = resolver.resolve({'underlying': 'GOLD', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'GOLDM26FEB')

    def test_nse_option_monthly(self):
        resolver = SymbolResolver(MOCK_CSV)

        # Test Monthly Preference -> Should get 26th Feb
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'MONTHLY', 'exchange': 'NFO'})
        self.assertEqual(res['expiry'], '2026-02-26')

        # Test Weekly Preference -> Should get nearest (5th Feb)
        # Assuming current date is before Feb 5th.
        # Note: SymbolResolver compares against datetime.now().
        # Since I'm using future dates (2026), it should work regardless of today (unless today is > 2026).
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'WEEKLY', 'exchange': 'NFO'})
        self.assertEqual(res['expiry'], '2026-02-05')

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    unittest.main()
