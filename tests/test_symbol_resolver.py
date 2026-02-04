import unittest
import pandas as pd
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):

    def setUp(self):
        # Create a mock dataframe
        now = datetime.now()

        # Helper to get expiry dates
        def next_expiry(days):
            return (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

        data = [
            # MCX GOLD - Standard vs MINI
            {'exchange': 'MCX', 'symbol': 'GOLD23OCTFUT', 'name': 'GOLD', 'expiry': next_expiry(20), 'lot_size': 100, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'GOLDM23OCTFUT', 'name': 'GOLD', 'expiry': next_expiry(20), 'lot_size': 10, 'instrument_type': 'FUT'},

            # MCX SILVER - Standard vs MINI vs MICRO (Prefer smallest)
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': next_expiry(40), 'lot_size': 30, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'SILVERM23NOVFUT', 'name': 'SILVER', 'expiry': next_expiry(40), 'lot_size': 5, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': next_expiry(40), 'lot_size': 1, 'instrument_type': 'FUT'},

            # NSE Options - Weekly vs Monthly
            # Assume 'now' is beginning of month.
            # Weekly 1: +2 days, Weekly 2: +9 days, Monthly: +30 days (End of month)
        ]

        # Add NSE Options
        # Ensure both are in the same month for the logic to work as expected by the test case
        # We'll use a fixed future date relative to 'now' but ensure they share month/year

        # Calculate a date in the middle of next month to be safe
        next_month = (now + timedelta(days=35)).replace(day=1)
        m1_weekly = next_month.replace(day=5)
        m1_monthly = next_month.replace(day=25) # Later in same month

        data.extend([
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': m1_weekly, 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': m1_monthly, 'lot_size': 50, 'instrument_type': 'OPT'}
        ])

        self.df = pd.DataFrame(data)

        # Patch load_instruments to use our mock df
        self.patcher = patch.object(SymbolResolver, 'load_instruments')
        self.mock_load = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_mcx_mini_preference(self):
        resolver = SymbolResolver(instruments_path='dummy.csv')
        resolver.df = self.df # Inject mock data

        # Case 1: GOLD - Should pick GOLDM (10 lot) over GOLD (100 lot)
        res = resolver.resolve({'underlying': 'GOLD', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'GOLDM23OCTFUT', "Should prefer GOLDM over GOLD")

    def test_mcx_smallest_lot_preference(self):
        resolver = SymbolResolver(instruments_path='dummy.csv')
        resolver.df = self.df

        # Case 2: SILVER - Should pick SILVERMIC (1 lot) over SILVERM (5) and SILVER (30)
        res = resolver.resolve({'underlying': 'SILVER', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVERMIC23NOVFUT', "Should prefer SILVERMIC (smallest lot)")

    def test_nse_option_weekly(self):
        resolver = SymbolResolver(instruments_path='dummy.csv')
        resolver.df = self.df

        # Case 3: Weekly Preference (default)
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'WEEKLY'})
        self.assertEqual(res['sample_symbol'], 'NIFTY23OCT19500CE', "Should pick nearest expiry")

    def test_nse_option_monthly(self):
        resolver = SymbolResolver(instruments_path='dummy.csv')
        resolver.df = self.df

        # Case 4: Monthly Preference
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'MONTHLY'})
        self.assertEqual(res['sample_symbol'], 'NIFTY23OCT19600CE', "Should pick monthly expiry")

if __name__ == '__main__':
    unittest.main()
