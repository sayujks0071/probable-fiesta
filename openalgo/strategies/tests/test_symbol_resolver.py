import unittest
import pandas as pd
import os
import shutil
from datetime import datetime, timedelta
import tempfile
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.test_dir, 'instruments.csv')

        # Create mock data
        now = datetime.now()
        # Find next Thursday
        days_ahead = 3 - now.weekday()
        if days_ahead < 0: days_ahead += 7
        next_thursday = now + timedelta(days=days_ahead)

        # Monthly Expiry (end of current month)
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = datetime(now.year, now.month, last_day)
        offset = (month_end.weekday() - 3) % 7
        monthly_expiry = month_end - timedelta(days=offset)

        # Next Month Expiry
        next_month = now + timedelta(days=32)
        last_day_next = calendar.monthrange(next_month.year, next_month.month)[1]
        next_month_end = datetime(next_month.year, next_month.month, last_day_next)
        offset_next = (next_month_end.weekday() - 3) % 7
        next_monthly_expiry = next_month_end - timedelta(days=offset_next)

        self.mock_data = [
            # NSE Equity
            {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},

            # NSE Futures
            {'exchange': 'NFO', 'token': '2', 'symbol': 'NIFTY23OCTFUT', 'name': 'NIFTY', 'expiry': monthly_expiry, 'lot_size': 50, 'instrument_type': 'FUT'},

            # MCX Futures (Standard & MINI)
            # Standard (Lot Size 30)
            {'exchange': 'MCX', 'token': '3', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': next_month, 'lot_size': 30, 'instrument_type': 'FUT'},
            # MINI/MICRO (Smallest Lot Size 5)
            {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': next_month, 'lot_size': 5, 'instrument_type': 'FUT'},

            # NSE Options (Weekly)
            {'exchange': 'NFO', 'token': '5', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': next_thursday, 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'token': '6', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': next_thursday, 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19600},

            # NSE Options (Monthly)
            {'exchange': 'NFO', 'token': '7', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': monthly_expiry, 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
        ]

        pd.DataFrame(self.mock_data).to_csv(self.csv_path, index=False)
        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_equity_resolution(self):
        # Test exact match
        res = self.resolver.resolve({'underlying': 'RELIANCE', 'type': 'EQUITY'})
        self.assertEqual(res, 'RELIANCE')

        # Test not found
        res = self.resolver.resolve({'underlying': 'UNKNOWN', 'type': 'EQUITY'})
        self.assertEqual(res, 'UNKNOWN')

    def test_mcx_mini_preference(self):
        # SILVER has both Standard (30) and MIC (5)
        # Should pick MIC due to lot_size logic
        res = self.resolver.resolve({'underlying': 'SILVER', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVERMIC23NOVFUT')

    def test_option_expiry_weekly(self):
        config = {'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'WEEKLY', 'option_type': 'CE'}
        valid = self.resolver.resolve(config)

        self.assertIsNotNone(valid)
        self.assertEqual(valid['status'], 'valid')
        # Check date (should match mock expiry which is next_thursday)
        # We assume test runs such that next_thursday is correctly mocked.
        # But 'resolve' returns validation dict.
        # Let's use get_tradable_symbol to verify actual symbol returned.

        # For get_tradable_symbol we need spot price
        sym = self.resolver.get_tradable_symbol(config, spot_price=19500)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

    def test_option_expiry_monthly(self):
        config = {'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'MONTHLY', 'option_type': 'PE'}
        # Should pick monthly expiry PE
        # Note: In mock data, PE only exists for Monthly expiry.
        sym = self.resolver.get_tradable_symbol(config, spot_price=19500)
        self.assertEqual(sym, 'NIFTY23OCT19500PE')

if __name__ == '__main__':
    unittest.main()
