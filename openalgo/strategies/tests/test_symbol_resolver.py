import unittest
import pandas as pd
import os
import tempfile
from datetime import datetime, timedelta
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        # Create dummy instruments data
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w')

        now = datetime.now()
        # Dates
        self.today = now
        self.next_week = now + timedelta(days=7)
        self.next_month = now + timedelta(days=30)

        # Determine monthly expiry (end of this month vs next)
        # Simplified for testing

        self.csv_path = self.temp_file.name

        # Write Header
        self.temp_file.write("exchange,token,symbol,name,expiry,lot_size,instrument_type,strike\n")

        # 1. NSE Equity
        self.temp_file.write("NSE,1,RELIANCE,RELIANCE,,1,EQ,\n")

        # 2. MCX Futures (Standard vs Mini)
        # Expiry: same date
        exp = (now + timedelta(days=10)).strftime('%Y-%m-%d')
        self.temp_file.write(f"MCX,2,SILVERMIC23NOV,SILVER,{exp},1,FUT,\n") # Mini (Lot 1)
        self.temp_file.write(f"MCX,3,SILVER23NOV,SILVER,{exp},30,FUT,\n") # Standard (Lot 30)

        # 3. NSE Options (Weekly vs Monthly)
        exp_w = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        exp_m = (now + timedelta(days=25)).strftime('%Y-%m-%d')

        # NIFTY Weekly
        self.temp_file.write(f"NFO,4,NIFTY23OCT19500CE,NIFTY,{exp_w},50,OPT,19500\n")
        self.temp_file.write(f"NFO,5,NIFTY23OCT19500PE,NIFTY,{exp_w},50,OPT,19500\n")

        # NIFTY Monthly
        self.temp_file.write(f"NFO,6,NIFTY23OCT19600CE,NIFTY,{exp_m},50,OPT,19600\n")

        self.temp_file.close()

        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        os.remove(self.csv_path)

    def test_equity_resolution(self):
        res = self.resolver.resolve({'type': 'EQUITY', 'symbol': 'RELIANCE'})
        self.assertEqual(res, 'RELIANCE')

    def test_mcx_mini_preference(self):
        # Should prefer SILVERMIC (Lot 1) over SILVER (Lot 30)
        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVERMIC23NOV')

    def test_option_expiry_weekly(self):
        # Should pick nearest expiry (Weekly)
        res = self.resolver.resolve({'type': 'OPT', 'underlying': 'NIFTY', 'expiry_preference': 'WEEKLY'})
        self.assertIsNotNone(res)
        self.assertEqual(res['status'], 'valid')
        # Expect the weekly expiry date
        expected_expiry = (self.today + timedelta(days=2)).strftime('%Y-%m-%d')
        self.assertEqual(res['expiry'], expected_expiry)

    def test_option_strike_selection(self):
        # Spot 19510 -> ATM 19500
        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT',
            'underlying': 'NIFTY',
            'option_type': 'CE',
            'expiry_preference': 'WEEKLY',
            'strike_criteria': 'ATM'
        }, spot_price=19510)

        self.assertEqual(sym, 'NIFTY23OCT19500CE')

if __name__ == '__main__':
    unittest.main()
