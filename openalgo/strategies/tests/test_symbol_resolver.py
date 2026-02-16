import unittest
import pandas as pd
import os
import shutil
from datetime import datetime, timedelta
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        self.test_dir = 'test_data'
        os.makedirs(self.test_dir, exist_ok=True)
        self.csv_path = os.path.join(self.test_dir, 'instruments.csv')

        # Create Mock Data
        now = datetime.now()
        # Ensure future dates
        future_date = now + timedelta(days=30)
        future_date_str = future_date.strftime('%Y-%m-%d')

        next_thursday = now + timedelta(days=(3-now.weekday()) % 7)
        if next_thursday <= now: next_thursday += timedelta(days=7)

        month_end = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        monthly_expiry = month_end - timedelta(days=(month_end.weekday()-3)%7)
        if monthly_expiry < now:
             # Move to next month
             month_end = (month_end + timedelta(days=32)).replace(day=1) - timedelta(days=1)
             monthly_expiry = month_end - timedelta(days=(month_end.weekday()-3)%7)

        self.data = [
            # Equity
            {'exchange': 'NSE', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'instrument_type': 'EQ'},

            # MCX Futures (Standard & MINI)
            # Dynamic expiry
            {'exchange': 'MCX', 'symbol': 'SILVERMICFUT', 'name': 'SILVERM', 'expiry': future_date_str, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'SILVERFUT', 'name': 'SILVER', 'expiry': future_date_str, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'GOLDMFUT', 'name': 'GOLDM', 'expiry': future_date_str, 'instrument_type': 'FUT'},

            # NSE Options
            {'exchange': 'NFO', 'symbol': 'NIFTYWEEKLYCE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'instrument_type': 'OPT', 'strike': 22000},
            {'exchange': 'NFO', 'symbol': 'NIFTYMONTHLYCE', 'name': 'NIFTY', 'expiry': monthly_expiry.strftime('%Y-%m-%d'), 'instrument_type': 'OPT', 'strike': 22000},
        ]

        pd.DataFrame(self.data).to_csv(self.csv_path, index=False)
        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_resolve_equity(self):
        res = self.resolver.resolve({'type': 'EQUITY', 'symbol': 'RELIANCE', 'exchange': 'NSE'})
        self.assertEqual(res, 'RELIANCE')

    def test_resolve_mcx_mini(self):
        # Should find MINI if available
        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'})
        # Should prefer SILVERMIC over SILVER
        self.assertIn('SILVERMIC', res)

    def test_resolve_mcx_standard_fallback(self):
        # Add CRUDEOIL without MINI
        future_date = datetime.now() + timedelta(days=30)
        new_data = {'exchange': 'MCX', 'symbol': 'CRUDEOILFUT', 'name': 'CRUDEOIL', 'expiry': future_date, 'instrument_type': 'FUT'}

        # Append and ensure datetime conversion
        new_df = pd.DataFrame([new_data])
        new_df['expiry'] = pd.to_datetime(new_df['expiry'])

        self.resolver.df = pd.concat([self.resolver.df, new_df], ignore_index=True)

        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'CRUDEOIL', 'exchange': 'MCX'})
        self.assertEqual(res, 'CRUDEOILFUT')

    def test_resolve_option_expiry(self):
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'MONTHLY'}
        res = self.resolver.resolve(config)
        self.assertEqual(res['status'], 'valid')
        self.assertIsNotNone(res['expiry'])

        # Verify it chose the monthly expiry (later one)
        # NIFTYMONTHLYCE
        # We can check count or underlying
        self.assertEqual(res['underlying'], 'NIFTY')

    def test_get_tradable_option(self):
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'WEEKLY', 'strike_criteria': 'ATM', 'option_type': 'CE'}
        # Spot 22000 -> Should pick 22000 CE (which is NIFTYWEEKLYCE in our mock)
        sym = self.resolver.get_tradable_option_symbol(config, spot_price=22000)
        self.assertEqual(sym, 'NIFTYWEEKLYCE')

if __name__ == '__main__':
    unittest.main()
