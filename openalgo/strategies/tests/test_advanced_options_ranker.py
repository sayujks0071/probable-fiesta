import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add strategies/scripts to path to import the script as module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

# Determine strategies root to add to sys.path for other imports
strategies_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if strategies_root not in sys.path:
    sys.path.append(strategies_root)

from advanced_options_ranker import MarketData, IronCondor, OptionStrategy
from openalgo.strategies.utils.trading_utils import APIClient

class TestAdvancedOptionsRanker(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=APIClient)
        self.md = MarketData(self.mock_client)

    @patch('advanced_options_ranker.requests.get')
    def test_market_data_update(self, mock_get):
        # Setup mock returns
        self.mock_client.get_quote.return_value = {'ltp': 18.5} # VIX
        self.mock_client.get_option_chain.return_value = [
            {'strike': 10000, 'ce': {'oi': 1000}, 'pe': {'oi': 800}},
            {'strike': 10100, 'ce': {'oi': 500}, 'pe': {'oi': 1200}}
        ]

        # Mock RSS Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <rss version="2.0">
            <channel>
                <item><title>Market Rally continues</title></item>
                <item><title>Positive vibes in Nifty</title></item>
            </channel>
        </rss>
        """
        mock_get.return_value = mock_response

        self.md.update_market_data()

        self.assertEqual(self.md.vix, 18.5)
        self.assertIn('NIFTY', self.md.data_cache)
        # Check Sentiment
        # 2 positive items, 0 negative. Count=2. Raw=1. Score=max(-1, min(1, 1*5)) = 1.0?
        # Wait, my logic: score += 1 for 'rally', 'positive'.
        # count=2. raw = 2/2 = 1. amplified = 5. capped at 1.0.
        self.assertEqual(self.md.sentiment_score, 1.0)

    def test_iron_condor_score(self):
        # Mock Market Data state
        self.md.vix = 18.0 # Good for IC
        self.md.data_cache = {
            'NIFTY': {
                'pcr': 1.0, # Neutral
                'max_pain': 10000
            }
        }

        # Determine IV Rank Mock
        # advanced_options_ranker.MarketData.get_iv_rank uses VIX heuristic
        # If VIX=18 (<20), Rank=60.

        strat = IronCondor("Test IC", "NIFTY", self.md)
        score = strat.calculate_score()

        # Expected Score Calculation:
        # IV Score = 60 * 0.35 = 21.0
        # VIX Score (15-25) = 100 * 0.25 = 25.0
        # PCR Score (0.8-1.2) = 100 * 0.20 = 20.0
        # Liquidity = 90 * 0.20 = 18.0
        # Total = 21 + 25 + 20 + 18 = 84.0

        self.assertAlmostEqual(score, 84.0, delta=1.0)

    def test_risk_params_high_vix(self):
        self.md.vix = 35.0
        strat = IronCondor("Test IC", "NIFTY", self.md)
        params = strat.get_risk_params()

        self.assertEqual(params['size_multiplier'], 0.5)
        self.assertEqual(params['stop_loss_pct'], 4.0)

    def test_risk_params_low_vix(self):
        self.md.vix = 10.0
        strat = IronCondor("Test IC", "NIFTY", self.md)
        params = strat.get_risk_params()

        self.assertEqual(params['size_multiplier'], 0.8) # Low premiums
        self.assertEqual(params['stop_loss_pct'], 2.0)

if __name__ == '__main__':
    unittest.main()
