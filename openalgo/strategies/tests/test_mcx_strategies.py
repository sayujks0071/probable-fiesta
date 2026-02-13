import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os

# Ensure paths are correct
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from openalgo.strategies.scripts.pairs_trading_mean_reversion import PairsTradingStrategy
from openalgo.strategies.scripts.mcx_commodity_momentum_strategy import MCXMomentumStrategy

class TestMCXStrategies(unittest.TestCase):
    def setUp(self):
        self.api_client_mock = MagicMock()
        self.api_client_mock.history.return_value = pd.DataFrame()
        self.api_client_mock.placesmartorder.return_value = {'status': 'success'}

    def test_pairs_trading_init(self):
        strategy = PairsTradingStrategy("GOLDM05FEB26FUT", "SILVERM27FEB26FUT", "key", "host", {'z_entry':2, 'z_exit':0.5})
        self.assertEqual(strategy.exchange, "MCX")
        self.assertEqual(strategy.symbol_x, "GOLDM05FEB26FUT")

        # Test Order Execution
        strategy.client = self.api_client_mock
        strategy.execute_trade("GOLDM05FEB26FUT", "BUY", 1, 1000)

        # Verify call arguments
        args, kwargs = self.api_client_mock.placesmartorder.call_args
        self.assertEqual(kwargs['strategy'], "PairsTrading")
        self.assertEqual(kwargs['symbol'], "GOLDM05FEB26FUT")
        self.assertEqual(kwargs['exchange'], "MCX")

    def test_momentum_execute_trade(self):
        params = {'adx_threshold': 25}
        strategy = MCXMomentumStrategy("CRUDEOIL19FEB26FUT", "key", "host", params)
        strategy.client = self.api_client_mock

        strategy.execute_trade("BUY", 1)

        # Verify call arguments
        args, kwargs = self.api_client_mock.placesmartorder.call_args
        self.assertEqual(kwargs['strategy'], "MCX_Momentum")
        self.assertEqual(kwargs['symbol'], "CRUDEOIL19FEB26FUT")
        self.assertEqual(kwargs['exchange'], "MCX")

if __name__ == '__main__':
    unittest.main()
