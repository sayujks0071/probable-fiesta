import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add project root
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from openalgo.strategies.scripts.advanced_options_ranker import AdvancedOptionsRanker

class TestAdvancedOptionsRanker(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()

        # Mock VIX
        self.mock_client.get_vix.return_value = 22.0 # High VIX (>20)

        # Mock Quote
        self.mock_client.get_quote.return_value = {'ltp': 25000.0}

        # Mock Chain
        # Create a dummy chain
        self.mock_chain = [
            {'strike': 24900, 'ce': {'oi': 50000, 'iv': 20}, 'pe': {'oi': 40000, 'iv': 22}},
            {'strike': 25000, 'ce': {'oi': 100000, 'iv': 22}, 'pe': {'oi': 120000, 'iv': 24}}, # Max Pain likely here
            {'strike': 25100, 'ce': {'oi': 60000, 'iv': 21}, 'pe': {'oi': 30000, 'iv': 23}},
        ]
        self.mock_client.get_option_chain.return_value = self.mock_chain

    @patch('openalgo.strategies.scripts.advanced_options_ranker.APIClient')
    @patch('openalgo.strategies.scripts.advanced_options_ranker.requests.get')
    def test_ranker_logic(self, mock_requests, mock_api_client_cls):
        mock_api_client_cls.return_value = self.mock_client

        # Mock Sentiment Response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # XML with some positive words
        mock_resp.content = b"""<rss><channel><item><title>Market Rally surges to new high</title></item>
        <item><title>Bull run continues with profit booking</title></item></channel></rss>"""
        mock_requests.return_value = mock_resp

        ranker = AdvancedOptionsRanker(api_key="test", host="http://mock:5002")

        # Run report generation
        # Capture print output? Or just return value.
        # generate_report returns list of top strategies.

        top_strats = ranker.generate_report()

        self.assertIsInstance(top_strats, list)

        # Check if we got results
        if top_strats:
            first = top_strats[0]
            print(f"Top Strategy: {first['strategy']} - Score: {first['score']}")
            self.assertIn('score', first)
            self.assertIn('strategy', first)

            # Since VIX is 22 (High), Iron Condor should have decent score for VIX regime
            # But Sentiment is Bullish (Rally), so Iron Condor (Neutral) might be penalized on sentiment
            pass

    def test_vix_impact(self):
        # Test Low VIX behavior
        self.mock_client.get_vix.return_value = 11.0

        ranker = AdvancedOptionsRanker(api_key="test")
        ranker.client = self.mock_client # Inject mock

        # We need to bypass __init__ creating new client or mock it
        # Since we use dependency injection style in test_ranker_logic via patch,
        # let's just use the analyze_strategy method directly for unit testing.

        market_data = {
            'vix': 11.0,
            'nifty_spot': 25000,
            'gift_nifty': 25000,
            'gap_pct': 0.0,
            'sentiment_score': 0.5
        }

        # Analyze Iron Condor with Low VIX
        details = ranker.analyze_strategy("Iron Condor", "NIFTY", market_data, self.mock_chain)
        # VIX < 12 => VIX Regime Score should be low (10 in code)
        # Weights: VIX Regime * 0.10

        print(f"Iron Condor Low VIX Score: {details['score']}")

        # Analyze Debit Spread with Low VIX
        details_ds = ranker.analyze_strategy("Debit Spread", "NIFTY", market_data, self.mock_chain)
        print(f"Debit Spread Low VIX Score: {details_ds['score']}")

        # Debit spread should likely score higher on VIX component
        # VIX < 15 => VIX Score 90 for Debit Spread
        # Iron Condor => VIX Score 20 or 10

        # Just verifying it runs without error and produces scores
        self.assertIsNotNone(details['score'])
        self.assertIsNotNone(details_ds['score'])

if __name__ == '__main__':
    unittest.main()
