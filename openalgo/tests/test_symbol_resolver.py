import unittest
import pandas as pd
import os
import tempfile
import logging
from datetime import datetime, timedelta
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

# Suppress logging during tests
# logging.disable(logging.CRITICAL)
logging.basicConfig(level=logging.DEBUG)

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, 'instruments.csv')

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_mock_data(self, data):
        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)
        return SymbolResolver(self.csv_path)

    def test_mcx_mini_preference(self):
        """Test that MCX MINI contracts are preferred over standard."""
        now = datetime.now()
        expiry = now + timedelta(days=30)
        data = [
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': expiry, 'lot_size': 30, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': expiry, 'lot_size': 1, 'instrument_type': 'FUT'},
        ]
        resolver = self.create_mock_data(data)
        res = resolver.resolve({'underlying': 'SILVER', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVERMIC23NOVFUT')

    def test_mcx_fallback_smallest_lot(self):
        """Test fallback to smallest lot size if no MINI name match."""
        now = datetime.now()
        expiry = now + timedelta(days=30)
        data = [
            {'exchange': 'MCX', 'symbol': 'SILVERBIG23NOVFUT', 'name': 'SILVER', 'expiry': expiry, 'lot_size': 100, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': expiry, 'lot_size': 30, 'instrument_type': 'FUT'},
        ]
        resolver = self.create_mock_data(data)
        res = resolver.resolve({'underlying': 'SILVER', 'type': 'FUT', 'exchange': 'MCX'})
        self.assertEqual(res, 'SILVER23NOVFUT')

    def test_monthly_expiry_logic(self):
        """Test Weekly vs Monthly expiry selection."""
        now = datetime.now()

        # Construct dates for next month to ensure they are in future
        target_year = now.year
        target_month = now.month + 1
        if target_month > 12:
            target_month = 1
            target_year += 1

        exp_w = datetime(target_year, target_month, 5)
        exp_m = datetime(target_year, target_month, 25)

        data = [
            {'exchange': 'NFO', 'symbol': 'NIFTYWCE', 'name': 'NIFTY', 'expiry': exp_w, 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'symbol': 'NIFTYMCE', 'name': 'NIFTY', 'expiry': exp_m, 'lot_size': 50, 'instrument_type': 'OPT'},
        ]
        resolver = self.create_mock_data(data)

        # Weekly
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'WEEKLY'})
        self.assertEqual(res['sample_symbol'], 'NIFTYWCE')

        # Monthly (should pick last expiry of the month of the nearest expiry)
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'MONTHLY'})
        self.assertEqual(res['sample_symbol'], 'NIFTYMCE')

    def test_expiry_rollover(self):
        """Test that if current month expiry passed, it picks next month."""
        # This is implicitly handled by `unique_expiries` containing only future dates (SymbolResolver implementation filters >= now).
        # But let's verify logic works given such a filtered list.

        now = datetime.now()
        # Expiry 1: Next Month Weekly
        # Expiry 2: Next Month Monthly

        target_year = now.year
        target_month = now.month + 1
        if target_month > 12:
            target_month = 1
            target_year += 1

        exp_w = datetime(target_year, target_month, 5)
        exp_m = datetime(target_year, target_month, 25)

        data = [
            {'exchange': 'NFO', 'symbol': 'NIFTYWCE', 'name': 'NIFTY', 'expiry': exp_w, 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'symbol': 'NIFTYMCE', 'name': 'NIFTY', 'expiry': exp_m, 'lot_size': 50, 'instrument_type': 'OPT'},
        ]
        resolver = self.create_mock_data(data)

        # Even if we ask for MONTHLY, it should pick NIFTYM (which is in next month)
        res = resolver.resolve({'underlying': 'NIFTY', 'type': 'OPT', 'expiry_preference': 'MONTHLY'})
        self.assertEqual(res['sample_symbol'], 'NIFTYMCE')

if __name__ == '__main__':
    unittest.main()
