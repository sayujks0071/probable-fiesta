import unittest
import pandas as pd
import os
import shutil
from datetime import datetime, timedelta
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolverExtended(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/data_ext"
        os.makedirs(self.test_dir, exist_ok=True)
        self.csv_path = os.path.join(self.test_dir, "instruments.csv")

        # Mock Data Setup
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Calculate Expiries
        # 1. Near Week (This Thursday or Next)
        days_ahead = (3 - now.weekday()) % 7
        if days_ahead == 0: days_ahead = 0 # Today is Thursday
        near_expiry = now + timedelta(days=days_ahead)

        # 2. Next Week
        next_expiry = near_expiry + timedelta(days=7)

        # 3. Month End Expiry (Last Thursday of Month)
        # To test Monthly preference effectively, we need W1 and M1 to be in the SAME month.
        # Let's force expiry_w1 to be 1st of next month, and expiry_m1 to be end of next month.

        # Move to next month start
        if now.month == 12:
            next_month = now.replace(year=now.year+1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month+1, day=1)

        days_ahead_nm = (3 - next_month.weekday()) % 7
        if days_ahead_nm == 0: days_ahead_nm = 0

        expiry_w1 = next_month + timedelta(days=days_ahead_nm) # 1st Thursday of next month
        expiry_m1 = expiry_w1 + timedelta(days=21) # 4th Thursday of next month (approx end)

        data = [
            # MCX Cases
            # 1. SILVER (Standard + MIC + M)
            # Assign Lot Sizes: Standard=30, Mini=5, Micro=1
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': expiry_m1, 'instrument_type': 'FUT', 'lot_size': 30},
            {'exchange': 'MCX', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': expiry_m1, 'instrument_type': 'FUT', 'lot_size': 1},
            {'exchange': 'MCX', 'symbol': 'SILVERM23NOVFUT', 'name': 'SILVER', 'expiry': expiry_m1, 'instrument_type': 'FUT', 'lot_size': 5},

            # 2. GOLD (Standard + M only)
            # Standard=100, Mini=10
            {'exchange': 'MCX', 'symbol': 'GOLD23NOVFUT', 'name': 'GOLD', 'expiry': expiry_m1, 'instrument_type': 'FUT', 'lot_size': 100},
            {'exchange': 'MCX', 'symbol': 'GOLDM23NOVFUT', 'name': 'GOLD', 'expiry': expiry_m1, 'instrument_type': 'FUT', 'lot_size': 10},

            # 3. CRUDEOIL (Standard only - Fallback Test)
            {'exchange': 'MCX', 'symbol': 'CRUDEOIL23NOVFUT', 'name': 'CRUDEOIL', 'expiry': expiry_m1, 'instrument_type': 'FUT', 'lot_size': 100},

            # NSE Options Cases
            # Name: NIFTY
            # Expiries: W1, W2, M1
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': expiry_w1, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': expiry_w1, 'instrument_type': 'OPT', 'strike': 19600},

            {'exchange': 'NFO', 'symbol': 'NIFTY23NOV19500CE', 'name': 'NIFTY', 'expiry': expiry_m1, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'symbol': 'NIFTY23NOV19600CE', 'name': 'NIFTY', 'expiry': expiry_m1, 'instrument_type': 'OPT', 'strike': 19600},

             # Validating Strike Selection Logic for CE/PE
             {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': expiry_w1, 'instrument_type': 'OPT', 'strike': 19500},
             {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19600PE', 'name': 'NIFTY', 'expiry': expiry_w1, 'instrument_type': 'OPT', 'strike': 19600},
        ]

        df = pd.DataFrame(data)
        # Ensure expiry is datetime
        df['expiry'] = pd.to_datetime(df['expiry'])
        df.to_csv(self.csv_path, index=False)

        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_mcx_mini_silver(self):
        # SILVER has MIC, M, and Standard. Should prefer MIC or M.
        # Logic says: prefer 'MINI' then 'M'.
        # SILVERMIC contains 'MIC'.
        # SILVERM contains 'M'.
        # Let's see what logic we implement. Ideally 'MIC' > 'M' > Standard for SILVER?
        # Or just any 'MINI' variant.

        config = {'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'}
        res = self.resolver.resolve(config)
        # Currently the logic might be ambiguous or pick first found 'MINI'.
        # We want to ensure it is NOT 'SILVER23NOVFUT' (Standard)
        self.assertNotEqual(res, 'SILVER23NOVFUT')
        # It should be one of the mini variants
        self.assertTrue('MIC' in res or 'M' in res)

    def test_mcx_mini_gold(self):
        # GOLD has M and Standard. Should pick M.
        config = {'type': 'FUT', 'underlying': 'GOLD', 'exchange': 'MCX'}
        res = self.resolver.resolve(config)
        self.assertEqual(res, 'GOLDM23NOVFUT')

    def test_mcx_fallback_crude(self):
        # CRUDEOIL has only Standard. Should fallback.
        config = {'type': 'FUT', 'underlying': 'CRUDEOIL', 'exchange': 'MCX'}
        res = self.resolver.resolve(config)
        self.assertEqual(res, 'CRUDEOIL23NOVFUT')

    def test_option_expiry_weekly(self):
        # Weekly should pick nearest expiry (W1)
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'WEEKLY', 'option_type': 'CE'}
        res = self.resolver.resolve(config)
        self.assertEqual(res['status'], 'valid')
        # Check date is W1
        # Since we can't easily check date object, check sample symbol
        self.assertTrue('OCT' in res['sample_symbol']) # W1 was OCT (mocked)

    def test_option_expiry_monthly(self):
        # Monthly should pick M1 (Nov)
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'MONTHLY', 'option_type': 'CE'}
        res = self.resolver.resolve(config)
        self.assertEqual(res['status'], 'valid')
        self.assertTrue('NOV' in res['sample_symbol']) # M1 was NOV

    def test_option_strike_itm_call(self):
        # Spot 19560. ATM 19600.
        # ITM Call = Strike < Spot. -> 19500.
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'option_type': 'CE', 'strike_criteria': 'ITM'}
        sym = self.resolver.get_tradable_symbol(config, spot_price=19560)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

    def test_option_strike_itm_put(self):
        # Spot 19540. ATM 19500.
        # ITM Put = Strike > Spot. -> 19600.
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'option_type': 'PE', 'strike_criteria': 'ITM'}
        sym = self.resolver.get_tradable_symbol(config, spot_price=19540)
        self.assertEqual(sym, 'NIFTY23OCT19600PE')

if __name__ == '__main__':
    unittest.main()
