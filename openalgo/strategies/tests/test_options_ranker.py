import sys
import os
import unittest
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.scripts.advanced_options_ranker import AdvancedOptionsRanker
from openalgo.strategies.scripts.sentiment_reversal_strategy import SentimentReversalStrategy
from openalgo.strategies.scripts.gap_fade_strategy import GapFadeStrategy
from openalgo.strategies.scripts.delta_neutral_iron_condor_nifty import DeltaNeutralIronCondor

class TestOptionsStrategies(unittest.TestCase):
    def test_ranker_instantiation(self):
        ranker = AdvancedOptionsRanker(api_key="test", host="http://127.0.0.1:5002")
        self.assertIsNotNone(ranker)
        self.assertEqual(ranker.weights['iv_rank'], 0.25)

    def test_sentiment_reversal_instantiation(self):
        strat = SentimentReversalStrategy(api_client=None, symbol="NIFTY", qty=10, sentiment_score=0.9)
        self.assertIsNotNone(strat)
        self.assertEqual(strat.sentiment_score, 0.9)

    def test_gap_fade_instantiation(self):
        strat = GapFadeStrategy(api_client=None, symbol="NIFTY", qty=10, threshold=0.5)
        self.assertIsNotNone(strat)
        self.assertEqual(strat.gap_threshold, 0.5)

    def test_iron_condor_instantiation(self):
        strat = DeltaNeutralIronCondor(api_client=None, symbol="NIFTY", qty=10, sentiment_score=0.5)
        self.assertIsNotNone(strat)
        self.assertEqual(strat.sentiment_score, 0.5)

if __name__ == '__main__':
    unittest.main()
