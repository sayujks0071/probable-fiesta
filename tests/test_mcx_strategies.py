import unittest
import sys
import os
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime

# Adjust path to import strategies
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../openalgo/strategies/scripts')))

# Mock modules before importing strategies
sys.modules['trading_utils'] = MagicMock()
sys.modules['symbol_resolver'] = MagicMock()
sys.modules['yfinance'] = MagicMock()

# Import Strategies
from openalgo.strategies.scripts.mcx_advanced_strategy import AdvancedMCXStrategy
from openalgo.strategies.scripts.mcx_commodity_momentum_strategy import MCXMomentumStrategy

class TestMCXStrategies(unittest.TestCase):

    def setUp(self):
        self.mock_api_key = "test_key"
        self.mock_host = "http://localhost:5001"

    def test_advanced_strategy_indicators(self):
        """Test MACD and Bollinger Bands calculation."""
        strategy = AdvancedMCXStrategy(self.mock_api_key, self.mock_host)

        # Create dummy DF
        dates = pd.date_range(start="2023-01-01", periods=50, freq="15min")
        data = {
            'close': np.random.normal(100, 10, 50).tolist(),
            'high': np.random.normal(105, 10, 50).tolist(),
            'low': np.random.normal(95, 10, 50).tolist(),
            'volume': [1000] * 50
        }
        df = pd.DataFrame(data, index=dates)

        indicators = strategy.calculate_technical_indicators(df)

        self.assertIn('macd', indicators)
        self.assertIn('upper_band', indicators)
        self.assertIsNotNone(indicators['macd'])

    def test_advanced_strategy_scoring(self):
        """Test scoring logic."""
        strategy = AdvancedMCXStrategy(self.mock_api_key, self.mock_host)

        # Mock dependencies
        strategy.resolver.resolve.return_value = "GOLDM05FEB26FUT"
        strategy.client.history.return_value = pd.DataFrame({
            'close': [100, 101, 102] * 20, # Up trend
            'high': [105] * 60,
            'low': [95] * 60,
            'volume': [2000] * 60
        })
        strategy.client.get_quote.return_value = {'ltp': 102, 'volume': 2000, 'oi': 500}

        # Mock Context
        strategy.market_context = {
            'usd_inr': 83.0,
            'usd_trend': 'Up',
            'usd_volatility': 0.5, # Low
        }

        strategy.commodities = [
            {'name': 'GOLD', 'global_ticker': 'GC=F', 'min_vol': 1000, 'valid': True}
        ]

        # Manually inject data to skip fetch
        df = pd.DataFrame({
            'close': np.linspace(100, 110, 60),
            'high': np.linspace(102, 112, 60),
            'low': np.linspace(98, 108, 60),
            'volume': [2000] * 60
        })
        strategy.commodities[0]['data'] = df
        strategy.commodities[0]['ltp'] = 110
        strategy.commodities[0]['volume'] = 2000
        strategy.commodities[0]['symbol'] = "GOLDM05FEB26FUT"

        strategy.analyze_commodities()

        self.assertTrue(len(strategy.opportunities) > 0)
        opp = strategy.opportunities[0]
        self.assertTrue(opp['score'] > 0)
        print(f"Test Opportunity Score: {opp['score']}")

    def test_momentum_strategy_expiry(self):
        """Test expiry parsing."""
        strategy = MCXMomentumStrategy("GOLD05FEB26FUT", "key", "host", {})

        expiry = strategy.parse_expiry("GOLD05FEB26FUT")
        self.assertEqual(expiry.year, 2026)
        self.assertEqual(expiry.month, 2)
        self.assertEqual(expiry.day, 5)

        expiry_fail = strategy.parse_expiry("INVALID")
        self.assertIsNone(expiry_fail)

    @patch('openalgo.strategies.scripts.mcx_commodity_momentum_strategy.is_market_open')
    def test_momentum_strategy_sizing(self, mock_market_open):
        """Test position sizing logic."""
        params = {
            'period_adx': 14, 'period_rsi': 14, 'period_atr': 14,
            'adx_threshold': 25, 'min_atr': 10, 'base_quantity': 10,
            'usd_inr_volatility': 1.5 # High Vol
        }
        # Use future contract relative to 2026 (sandbox time)
        strategy = MCXMomentumStrategy("GOLD05FEB27FUT", "key", "host", params)
        strategy.pm = MagicMock()
        strategy.pm.has_position.return_value = False

        # Mock Data
        dates = pd.date_range(start="2023-01-01", periods=60, freq="15min")
        df = pd.DataFrame({
            'close': np.linspace(100, 110, 60),
            'high': np.linspace(105, 115, 60),
            'low': np.linspace(95, 105, 60),
            'volume': [1000] * 60
        }, index=dates)

        # Make ATR High to trigger reduction
        # ATR calculation in script: rolling mean of range
        # Let's mock the check_signals directly or rely on calc

        strategy.data = df
        strategy.calculate_indicators()

        # Mock check_signals internals:
        # We can't easily mock local variables in a method.
        # But we can check logs or side effects (pm.update_position args)

        # Run check_signals
        with self.assertLogs('MCX_Momentum', level='INFO') as log:
            strategy.check_signals()

        # Verify warnings or sizing logs
        found_vol_warning = any("High USD/INR Volatility" in r.message for r in log.records)
        self.assertTrue(found_vol_warning)

if __name__ == '__main__':
    unittest.main()
