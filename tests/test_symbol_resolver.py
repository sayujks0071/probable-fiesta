import unittest
import pandas as pd
import os
import sys
from datetime import datetime, timedelta

# Add vendor path
sys.path.append(os.path.join(os.getcwd(), 'vendor'))
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        # Create a mock instruments.csv
        self.csv_path = 'test_instruments.csv'

        now = datetime.now()
        # Mock Expiries
        # Assuming today is before Nov 2026
        # Weekly expiries in Nov 2026
        self.nov2 = datetime(2026, 11, 5) # Thursday
        self.nov9 = datetime(2026, 11, 12)
        self.nov30 = datetime(2026, 11, 26) # Last Thursday

        data = [
            # NSE Options
            {'exchange': 'NFO', 'symbol': 'NIFTY26NOV19000CE', 'name': 'NIFTY', 'expiry': self.nov2, 'instrument_type': 'OPT', 'strike': 19000},
            {'exchange': 'NFO', 'symbol': 'NIFTY26NOV19000PE', 'name': 'NIFTY', 'expiry': self.nov2, 'instrument_type': 'OPT', 'strike': 19000},
            {'exchange': 'NFO', 'symbol': 'NIFTY26NOV2619000CE', 'name': 'NIFTY', 'expiry': self.nov30, 'instrument_type': 'OPT', 'strike': 19000}, # Monthly

            # MCX Futures
            {'exchange': 'MCX', 'symbol': 'SILVER26NOVFUT', 'name': 'SILVER', 'expiry': self.nov30, 'instrument_type': 'FUT', 'lot_size': 30},
            {'exchange': 'MCX', 'symbol': 'SILVERMIC26NOVFUT', 'name': 'SILVER', 'expiry': self.nov30, 'instrument_type': 'FUT', 'lot_size': 1},
            {'exchange': 'MCX', 'symbol': 'SILVERM26NOVFUT', 'name': 'SILVER', 'expiry': self.nov30, 'instrument_type': 'FUT', 'lot_size': 5},

            {'exchange': 'MCX', 'symbol': 'GOLD26NOVFUT', 'name': 'GOLD', 'expiry': self.nov30, 'instrument_type': 'FUT', 'lot_size': 100},

            # Equity
            {'exchange': 'NSE', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'instrument_type': 'EQ', 'lot_size': 1},
        ]

        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)

        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def test_nse_weekly(self):
        config = {
            'underlying': 'NIFTY',
            'type': 'OPT',
            'expiry_preference': 'WEEKLY',
            'option_type': 'CE'
        }
        res = self.resolver.resolve(config)
        self.assertEqual(res['expiry'], self.nov2.strftime('%Y-%m-%d'))

    def test_nse_monthly(self):
        config = {
            'underlying': 'NIFTY',
            'type': 'OPT',
            'expiry_preference': 'MONTHLY',
            'option_type': 'CE'
        }
        res = self.resolver.resolve(config)
        # Should pick the last expiry in the same month as the nearest expiry
        # Nearest is Nov 2. Last in Nov is Nov 30.
        self.assertEqual(res['expiry'], self.nov30.strftime('%Y-%m-%d'))

    def test_mcx_mini_preference(self):
        # SILVER has 30, 5, 1 lot sizes. Should pick 1 (MIC).
        sym = self.resolver._resolve_future('SILVER', 'MCX')
        self.assertEqual(sym, 'SILVERMIC26NOVFUT')

    def test_mcx_fallback(self):
        # GOLD only has 100 lot size.
        sym = self.resolver._resolve_future('GOLD', 'MCX')
        self.assertEqual(sym, 'GOLD26NOVFUT')

    def test_equity_resolve(self):
        sym = self.resolver.resolve({'symbol': 'RELIANCE', 'type': 'EQUITY', 'exchange': 'NSE'})
        self.assertEqual(sym, 'RELIANCE')

if __name__ == '__main__':
    unittest.main()
