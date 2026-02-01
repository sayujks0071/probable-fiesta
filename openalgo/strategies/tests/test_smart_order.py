import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from openalgo.strategies.utils.trading_utils import SmartOrder

class TestSmartOrder(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.smart_order = SmartOrder(self.mock_client)
        self.strategy = "TestStrategy"
        self.symbol = "RELIANCE"
        self.exchange = "NSE"
        self.quantity = 1

    def test_place_adaptive_order_medium_urgency_no_limit(self):
        """
        Test that MEDIUM urgency without limit price triggers slippage protection (Market -> Limit).
        """
        # Mock get_quote to return a valid LTP
        self.mock_client.get_quote.return_value = {'ltp': 1000.0}

        # Call with defaults (urgency='MEDIUM')
        self.smart_order.place_adaptive_order(
            self.strategy, self.symbol, "BUY", self.exchange, self.quantity
        )

        # Expected Limit Price: 1000 * 1.005 = 1005.0
        self.mock_client.placesmartorder.assert_called_with(
            strategy=self.strategy,
            symbol=self.symbol,
            action="BUY",
            exchange=self.exchange,
            price_type="LIMIT", # Should be converted to LIMIT
            product="MIS",
            quantity=self.quantity,
            position_size=self.quantity,
            price=1005.0
        )

    def test_place_adaptive_order_high_urgency(self):
        """Test HIGH urgency uses MARKET order."""
        self.smart_order.place_adaptive_order(
            self.strategy, self.symbol, "BUY", self.exchange, self.quantity, urgency='HIGH'
        )

        self.mock_client.placesmartorder.assert_called()
        call_args = self.mock_client.placesmartorder.call_args
        self.assertEqual(call_args.kwargs['price_type'], "MARKET")
        self.assertEqual(call_args.kwargs['price'], 0)

if __name__ == '__main__':
    unittest.main()
