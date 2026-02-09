import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.scripts.advanced_options_ranker import AdvancedOptionsRanker

class TestAdvancedOptionsRanker(unittest.TestCase):
    def setUp(self):
        self.ranker = AdvancedOptionsRanker(api_key="test")
        self.ranker.client = MagicMock()

    def test_market_data_fetching(self):
        # Mock API responses
        self.ranker.client.get_quote.side_effect = lambda sym, ex: {'ltp': 22000} if "NIFTY" in sym else {'ltp': 15.0} # VIX
        self.ranker.client.get_option_chain.return_value = [
            {'strike': 22000, 'ce_oi': 1000, 'pe_oi': 2000, 'ce_iv': 20, 'pe_iv': 20},
            {'strike': 22100, 'ce_oi': 500, 'pe_oi': 1000, 'ce_iv': 22, 'pe_iv': 22}
        ]

        # Mock requests for sentiment
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = b'<rss><channel><item><title>Market jumps on positive news</title></item></channel></rss>'

            data = self.ranker.fetch_market_data()

            self.assertEqual(data['vix'], 15.0)
            self.assertEqual(data['nifty_spot'], 22000)
            self.assertIn('NIFTY', data['chains'])
            self.assertEqual(len(data['chains']['NIFTY']), 2)
            self.assertGreater(data['sentiment_score'], 0.5)

    def test_composite_score(self):
        scores = {
            "iv_rank": 50,
            "greeks": 50,
            "liquidity": 50,
            "pcr_oi": 50,
            "vix_regime": 50,
            "gift_nifty": 50,
            "sentiment": 50
        }
        # Weights sum to 1.0 (0.25+0.20+0.15+0.15+0.10+0.10+0.05 = 1.0)
        # So result should be 50
        score = self.ranker.calculate_composite_score(scores)
        self.assertAlmostEqual(score, 50.0)

    def test_analyze_strategy(self):
        market_data = {
            'vix': 25.0, # High VIX
            'nifty_spot': 22000,
            'sentiment_score': 0.6,
            'gap_pct': 0.1,
            'sentiment_label': "Neutral"
        }
        chain_data = [
            {'strike': 22000, 'ce_oi': 1000, 'pe_oi': 1000} # PCR = 1.0
        ]

        # Test Iron Condor (should like High VIX)
        details = self.ranker.analyze_strategy("Iron Condor", "NIFTY", market_data, chain_data)

        # Expect High VIX Score (100) -> 0.10 weight -> 10 points
        # Expect IV Rank High (calculated from VIX=25 -> rank ~ 75) -> 0.25 weight -> 18.75 points
        # Expect PCR Score High (PCR=1) -> 0.15 weight -> 13.5 points
        # Total should be decent

        self.assertGreater(details['score'], 50)
        # self.assertEqual(details['strategy'], "Iron Condor") # Not added by analyze_strategy, but by loop

    def test_report_generation(self):
         # Mock API responses for report
        self.ranker.client.get_quote.side_effect = lambda sym, ex: {'ltp': 22000} if "NIFTY" in sym else {'ltp': 15.0}
        self.ranker.client.get_option_chain.return_value = [{'strike': 22000, 'ce_oi': 1000, 'pe_oi': 1000}]

        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = b'<rss><channel><item><title>Neutral market</title></item></channel></rss>'

            # Capture stdout
            from io import StringIO
            captured_output = StringIO()
            sys.stdout = captured_output

            self.ranker.generate_report()

            sys.stdout = sys.__stdout__
            output = captured_output.getvalue()

            self.assertIn("DAILY OPTIONS STRATEGY ANALYSIS", output)
            self.assertIn("STRATEGY OPPORTUNITIES", output)
            self.assertIn("Iron Condor - NIFTY", output)

if __name__ == '__main__':
    unittest.main()
