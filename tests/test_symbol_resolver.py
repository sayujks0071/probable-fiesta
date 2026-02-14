import unittest
import pandas as pd
import os
import sys
import shutil
from datetime import datetime, timedelta

# Add repo root to sys.path to allow importing vendor
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Add vendor to sys.path so 'openalgo' imports work if needed inside the module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../vendor')))

from vendor.openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        # Create a mock instruments.csv
        self.test_dir = "tests/temp_data"
        os.makedirs(self.test_dir, exist_ok=True)
        self.csv_path = os.path.join(self.test_dir, "instruments.csv")

        # Determine dates
        self.now = datetime.now()

        self.d1 = self.now + timedelta(days=5)
        self.d2 = self.now + timedelta(days=12)
        # Ensure d_month_end is in same month as d1 for the monthly test to work as expected in this mock scenario
        # If d1 is late in month, d_month_end might be next month.
        # We force d_month_end to be later in same month if possible, or skip test logic.

        # Hardcode dates to avoid boundary issues in test
        # We assume "Month" is month of d1.
        self.d_month_end = self.d1.replace(day=28)
        if self.d_month_end < self.d1:
             # If d1 is 29th, then 28th is past.
             # Just use d1 + 20 days
             self.d_month_end = self.d1 + timedelta(days=20)

        data = [
            # MCX Silver: Standard vs Mini
            # Standard: Big Lot (30)
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': self.d1, 'lot_size': 30, 'instrument_type': 'FUT'},
            # Mini: Small Lot (5) + 'M' in symbol (but name is SILVER)
            {'exchange': 'MCX', 'symbol': 'SILVERM23NOVFUT', 'name': 'SILVER', 'expiry': self.d1, 'lot_size': 5, 'instrument_type': 'FUT'},

            # NSE Options
            # Weekly
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': self.d1, 'lot_size': 50, 'instrument_type': 'OPT'},
            # Next Weekly
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': self.d2, 'lot_size': 50, 'instrument_type': 'OPT'},
            # Monthly
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19700CE', 'name': 'NIFTY', 'expiry': self.d_month_end, 'lot_size': 50, 'instrument_type': 'OPT'},

            # Equity
            {'exchange': 'NSE', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'}
        ]

        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)

        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_mcx_mini_preference(self):
        # Should prefer SILVERM over SILVER
        config = {'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'}
        symbol = self.resolver.resolve(config)
        self.assertEqual(symbol, 'SILVERM23NOVFUT')

    def test_nse_equity(self):
        config = {'type': 'EQUITY', 'symbol': 'RELIANCE', 'exchange': 'NSE'}
        symbol = self.resolver.resolve(config)
        self.assertEqual(symbol, 'RELIANCE')

    def test_nse_option_weekly(self):
        # Default is Weekly (nearest)
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'WEEKLY'}
        res = self.resolver.resolve(config)
        # Should be d1
        self.assertEqual(pd.to_datetime(res['expiry']).date(), self.d1.date())

    def test_nse_option_monthly(self):
        # Preference Monthly
        # Only verify if d1 and d_month_end are in same month and d1 < d_month_end
        if self.d1.month == self.d_month_end.month and self.d1 < self.d_month_end:
            config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'MONTHLY'}
            res = self.resolver.resolve(config)
            self.assertEqual(pd.to_datetime(res['expiry']).date(), self.d_month_end.date())

if __name__ == '__main__':
    unittest.main()
