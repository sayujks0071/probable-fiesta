import unittest
import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import tempfile
import shutil

# Add vendor/openalgo to sys.path to allow importing strategies
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../vendor/openalgo')))

try:
    from strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    # Fallback/Retry with openalgo prefix if my structural assumption is wrong
    # But based on list_files, strategies is at root of vendor/openalgo
    try:
        from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    except ImportError:
        print("Failed to import SymbolResolver. check sys.path:", sys.path)
        raise

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.test_dir, 'instruments.csv')

        # Create mock instruments data
        now = datetime.now()

        # Expiries
        # Calculate next Thursday
        days_ahead = 3 - now.weekday()
        if days_ahead < 0: days_ahead += 7
        next_thursday = now + timedelta(days=days_ahead)

        # Monthly: Last Thursday of current month (approx)
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = datetime(now.year, now.month, last_day)
        # Backtrack to Thursday
        offset = (month_end.weekday() - 3) % 7
        monthly_expiry = month_end - timedelta(days=offset)

        # Ensure we have a valid future monthly expiry
        if monthly_expiry < now:
             # Move to next month
             if now.month == 12:
                 next_month = datetime(now.year + 1, 1, 31)
             else:
                 next_month = datetime(now.year, now.month + 1, 28) # Safety
             last_day_nm = calendar.monthrange(next_month.year, next_month.month)[1]
             month_end_nm = datetime(next_month.year, next_month.month, last_day_nm)
             monthly_expiry = month_end_nm - timedelta(days=(month_end_nm.weekday() - 3) % 7)

        self.data = [
            # Equities
            {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},

            # MCX Futures
            {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 1, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '5', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 30, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '6', 'symbol': 'GOLDM23NOVFUT', 'name': 'GOLD', 'expiry': (now + timedelta(days=25)).strftime('%Y-%m-%d'), 'lot_size': 10, 'instrument_type': 'FUT'},

            # NSE Options
            # ATM (19500)
            {'exchange': 'NFO', 'token': '10', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'token': '11', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
            # ITM/OTM
            {'exchange': 'NFO', 'token': '12', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19600},
            {'exchange': 'NFO', 'token': '13', 'symbol': 'NIFTY23OCT19400CE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19400},

            # Monthly
            {'exchange': 'NFO', 'token': '14', 'symbol': 'NIFTY23OCTM19500CE', 'name': 'NIFTY', 'expiry': monthly_expiry.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT', 'strike': 19500},
        ]

        pd.DataFrame(self.data).to_csv(self.csv_path, index=False)
        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_resolve_equity(self):
        res = self.resolver.resolve({'type': 'EQUITY', 'symbol': 'RELIANCE', 'exchange': 'NSE'})
        self.assertEqual(res, 'RELIANCE')

    def test_resolve_mcx_mini(self):
        # Should pick SILVERMIC (MINI) over SILVER (Standard)
        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVERMIC23NOVFUT')

    def test_resolve_mcx_mini_fallback(self):
        # Test explicit GOLDM pickup
        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'GOLD', 'exchange': 'MCX'})
        self.assertEqual(res, 'GOLDM23NOVFUT')

    def test_resolve_option_weekly(self):
        res = self.resolver.resolve({
            'type': 'OPT',
            'underlying': 'NIFTY',
            'exchange': 'NFO',
            'expiry_preference': 'WEEKLY',
            'option_type': 'CE'
        })
        self.assertIsInstance(res, dict)
        self.assertEqual(res['status'], 'valid')
        # Check expiry matches next thursday in our mock data
        self.assertTrue('NIFTY23OCT' in res['sample_symbol'])

    def test_get_tradable_symbol_atm(self):
        # Spot 19500 -> ATM 19500
        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT',
            'underlying': 'NIFTY',
            'exchange': 'NFO',
            'option_type': 'CE',
            'strike_criteria': 'ATM'
        }, spot_price=19505)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

    def test_get_tradable_symbol_itm(self):
        # Spot 19500 -> Call ITM = 19400 (Lower Strike)
        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT',
            'underlying': 'NIFTY',
            'exchange': 'NFO',
            'option_type': 'CE',
            'strike_criteria': 'ITM'
        }, spot_price=19505)
        self.assertEqual(sym, 'NIFTY23OCT19400CE')

    def test_get_tradable_symbol_otm(self):
        # Spot 19500 -> Call OTM = 19600 (Higher Strike)
        sym = self.resolver.get_tradable_symbol({
            'type': 'OPT',
            'underlying': 'NIFTY',
            'exchange': 'NFO',
            'option_type': 'CE',
            'strike_criteria': 'OTM'
        }, spot_price=19505)
        self.assertEqual(sym, 'NIFTY23OCT19600CE')

if __name__ == '__main__':
    unittest.main()
