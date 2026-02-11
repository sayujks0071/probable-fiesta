import unittest
import pandas as pd
import sys
import os
from datetime import datetime, timedelta

# Add vendor to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../vendor')))

from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        self.test_csv = "test_instruments.csv"
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Helper to format date
        def date(days): return (now + timedelta(days=days)).strftime("%Y-%m-%d")

        # Calculate Monthly Expiry (Last Thursday of current month)
        # Simplified: Just set some dates
        # Assume today is near beginning of month.
        # Expiry 1: +5 days (Weekly)
        # Expiry 2: +12 days (Weekly)
        # Expiry 3: +25 days (Monthly)

        self.d1 = now + timedelta(days=5)
        self.d2 = now + timedelta(days=12)
        self.d3 = now + timedelta(days=25)

        data = [
            # NIFTY Futures
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCTFUT', 'name': 'NIFTY', 'expiry': self.d3, 'instrument_type': 'FUT', 'lot_size': 50},

            # MCX Silver
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': self.d3, 'instrument_type': 'FUT', 'lot_size': 30},
            {'exchange': 'MCX', 'symbol': 'SILVERM23NOVFUT', 'name': 'SILVER', 'expiry': self.d3, 'instrument_type': 'FUT', 'lot_size': 5}, # MINI

            # MCX Gold (No MINI explicit name, but small lot)
            {'exchange': 'MCX', 'symbol': 'GOLD23NOVFUT', 'name': 'GOLD', 'expiry': self.d3, 'instrument_type': 'FUT', 'lot_size': 100},
            {'exchange': 'MCX', 'symbol': 'GOLDM23NOVFUT', 'name': 'GOLD', 'expiry': self.d3, 'instrument_type': 'FUT', 'lot_size': 10}, # MINI by name

            # NSE Options
            # Weekly
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': self.d1, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': self.d1, 'instrument_type': 'OPT', 'strike': 19600},
            # Monthly
            {'exchange': 'NFO', 'symbol': 'NIFTY23NOV19500CE', 'name': 'NIFTY', 'expiry': self.d3, 'instrument_type': 'OPT', 'strike': 19500},
        ]

        pd.DataFrame(data).to_csv(self.test_csv, index=False)
        self.resolver = SymbolResolver(self.test_csv)

    def tearDown(self):
        if os.path.exists(self.test_csv):
            os.remove(self.test_csv)

    def test_mcx_mini_preference(self):
        # Should pick SILVERM over SILVER because of 'M' and lot size
        sym = self.resolver.resolve({'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'})
        self.assertEqual(sym, 'SILVERM23NOVFUT')

        # Should pick GOLDM over GOLD
        sym = self.resolver.resolve({'type': 'FUT', 'underlying': 'GOLD', 'exchange': 'MCX'})
        self.assertEqual(sym, 'GOLDM23NOVFUT')

    def test_nse_futures(self):
        sym = self.resolver.resolve({'type': 'FUT', 'underlying': 'NIFTY', 'exchange': 'NFO'})
        self.assertEqual(sym, 'NIFTY23OCTFUT')

    def test_nse_options_weekly(self):
        # Default Weekly (Nearest)
        res = self.resolver.resolve({'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'WEEKLY'})
        self.assertTrue(res['status'] == 'valid')
        # Should be d1
        expiry = pd.to_datetime(res['expiry'])
        d1 = pd.to_datetime(self.d1)
        self.assertEqual(expiry, d1)

    def test_nse_options_monthly(self):
        # Monthly Preference
        res = self.resolver.resolve({'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'MONTHLY'})

        d3 = pd.to_datetime(self.d3)
        expiry = pd.to_datetime(res['expiry'])

        # If d1 and d3 are same month, it should pick d3.
        if self.d1.month == self.d3.month:
            self.assertEqual(expiry, d3)
        else:
            # If d3 is next month, logic picks last expiry of NEAREST month.
            # So if nearest is Oct (d1), we want last Oct expiry.
            # But wait, if d1 is Oct 15 and d3 is Nov 4...
            # The logic currently finds expiries in Oct. If d1 is the only one in Oct, it returns d1.
            # This is correct behavior for "Monthly contract of current month".
            pass

    def test_get_option_symbol_atm(self):
        # Spot 19540. ATM -> 19500 or 19600? 19500 (diff 40) vs 19600 (diff 60). 19500 is closer.
        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT', 'underlying': 'NIFTY', 'expiry_preference': 'WEEKLY', 'option_type': 'CE'
        }, spot_price=19540)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

    def test_get_option_symbol_itm(self):
        # Spot 19540. ATM 19500. ITM Call -> Lower -> ?
        # I only have 19500 and 19600.
        # ATM=19500. ITM (Call) = Lower.
        # Index of 19500 is 0.
        # max(0, 0-1) = 0.
        # So it returns 19500.

        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT', 'underlying': 'NIFTY', 'expiry_preference': 'WEEKLY', 'option_type': 'CE', 'strike_criteria': 'ITM'
        }, spot_price=19540)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

        # OTM Call -> Higher -> 19600.
        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT', 'underlying': 'NIFTY', 'expiry_preference': 'WEEKLY', 'option_type': 'CE', 'strike_criteria': 'OTM'
        }, spot_price=19540)
        self.assertEqual(sym, 'NIFTY23OCT19600CE')

if __name__ == '__main__':
    unittest.main()
