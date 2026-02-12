import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from openalgo.strategies.scripts.gap_fade_strategy import GapFadeStrategy

class TestGapFadeStrategy(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.get_vix.return_value = 15.0
        self.mock_client.get_quote.return_value = {'ltp': 20200.0, 'close': 20000.0} # Gap Up 1%

        # History mock for Prev Close
        # df with prev close 20000
        df = pd.DataFrame({
            'datetime': [pd.Timestamp.now() - pd.Timedelta(days=1)],
            'close': [20000.0]
        })
        self.mock_client.history.return_value = df

        # History mock for SMA (Trend Filter)
        # 250 days of rising prices -> Uptrend
        sma_df = pd.DataFrame({
            'datetime': pd.date_range(end=datetime.now(), periods=250),
            'close': [19000.0] * 250
        })
        # Last close 20000, SMA 200 is 19000. Price > SMA -> Uptrend.

        def history_side_effect(symbol, interval, **kwargs):
            if interval == "day" and "start_date" in kwargs:
                # Basic check to distinguish history calls
                # Assuming first call is for Prev Close (short range), second for SMA (long range)
                # Or based on length of range
                start = pd.to_datetime(kwargs['start_date'])
                if (datetime.now() - start).days > 10:
                    return sma_df
                return df
            return df

        self.mock_client.history.side_effect = history_side_effect

    @patch('openalgo.strategies.scripts.gap_fade_strategy.RiskManager')
    @patch('openalgo.strategies.scripts.gap_fade_strategy.SymbolResolver')
    def test_gap_up_fade_short_blocked_by_trend(self, MockResolver, MockRiskManager):
        # Scenario: Gap Up (20200 vs 20000). Trend is UP (20200 > 19000).
        # Fade Strategy wants to Short (Buy PE).
        # Trend Filter should BLOCK this because Shorting in Uptrend is dangerous.

        rm_instance = MockRiskManager.return_value
        rm_instance.can_trade.return_value = (True, "OK")

        resolver_instance = MockResolver.return_value
        resolver_instance.get_tradable_symbol.return_value = "NIFTY23OCT20200PE"

        strategy = GapFadeStrategy(self.mock_client, symbol="NIFTY", trend_filter=True)
        strategy.execute()

        # Should NOT register entry
        rm_instance.register_entry.assert_not_called()
        print("Test 1 Passed: Gap Up in Uptrend Blocked")

    @patch('openalgo.strategies.scripts.gap_fade_strategy.RiskManager')
    @patch('openalgo.strategies.scripts.gap_fade_strategy.SymbolResolver')
    def test_gap_down_fade_long_allowed_in_uptrend(self, MockResolver, MockRiskManager):
        # Scenario: Gap Down (19800 vs 20000). Trend is UP (19800 > 19000).
        # Fade Strategy wants to Long (Buy CE).
        # Trend Filter should ALLOW this because Buying in Uptrend is good.

        self.mock_client.get_quote.return_value = {'ltp': 19800.0, 'close': 20000.0} # Gap Down -1%

        rm_instance = MockRiskManager.return_value
        rm_instance.can_trade.return_value = (True, "OK")
        rm_instance.calculate_stop_loss.return_value = 90.0

        resolver_instance = MockResolver.return_value
        resolver_instance.get_tradable_symbol.return_value = "NIFTY23OCT19800CE"

        strategy = GapFadeStrategy(self.mock_client, symbol="NIFTY", trend_filter=True)
        strategy.execute()

        # Should register entry
        rm_instance.register_entry.assert_called_once()
        print("Test 2 Passed: Gap Down in Uptrend Allowed")

if __name__ == '__main__':
    unittest.main()
