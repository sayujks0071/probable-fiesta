import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import pandas as pd

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, repo_root)

# Mock modules that might be missing in environment
sys.modules['trading_utils'] = MagicMock()
sys.modules['mcx_utils'] = MagicMock()

from openalgo.strategies.scripts.mcx_advanced_strategy import GlobalMarketData, StrategyScorer, generate_daily_report

class TestMCXAdvancedStrategy(unittest.TestCase):

    @patch('yfinance.download')
    def test_global_data_fetch(self, mock_download):
        # Mock df structure returned by yfinance
        # It usually returns MultiIndex columns if multiple tickers
        # Structure: (PriceType, Ticker)
        data = {
            ('Close', 'GC=F'): [2000.0, 2010.0, 2020.0],
            ('Close', 'INR=X'): [83.0, 83.1, 83.2]
        }
        mock_df = pd.DataFrame(data)
        mock_download.return_value = mock_df

        gd = GlobalMarketData()
        gd.fetch_all()

        # Check if GOLD was processed
        # Note: TICKERS map 'GOLD' -> 'GC=F'
        self.assertIn('GOLD', gd.data)
        self.assertEqual(gd.data['GOLD']['trend'], 'Up')
        self.assertAlmostEqual(gd.data['GOLD']['price'], 2020.0)

    def test_scoring_logic(self):
        # Mock data
        g_data = {
            'GOLD': {'trend': 'Up', 'volatility': 1.0},
            'CRUDEOIL': {'trend': 'Down', 'volatility': 3.0}
        }
        m_data = {
            'GOLD': {},
            'CRUDEOIL': {}
        }

        scorer = StrategyScorer(g_data, m_data)

        # Test Gold (Up Trend, Moderate Vol)
        score_gold = scorer.calculate_score('GOLD')
        self.assertGreater(score_gold['composite'], 50)
        self.assertEqual(score_gold['components']['trend'], 70) # Up trend

        # Test Crude (Down Trend, High Vol)
        score_crude = scorer.calculate_score('CRUDEOIL')
        self.assertEqual(score_crude['components']['trend'], 30) # Down trend
        self.assertEqual(score_crude['components']['volatility'], 50) # High vol penalty

    def test_report_generation(self):
        g_data = {'USDINR': {'price': 83.5, 'trend': 'Neutral', 'volatility': 0.1}}
        scores = {
            'GOLD': {'composite': 80.5, 'components': {'trend': 80, 'momentum': 60, 'global': 80, 'volatility': 90, 'seasonality': 50}},
            'SILVER': {'composite': 45.0, 'components': {'trend': 30, 'momentum': 40, 'global': 50, 'volatility': 50, 'seasonality': 50}}
        }

        report = generate_daily_report(g_data, scores)
        self.assertIn("DAILY MCX STRATEGY ANALYSIS", report)
        self.assertIn("GOLD", report)
        self.assertIn("SILVER", report)
        self.assertIn("DEPLOY", report) # Gold > 70
        self.assertIn("MONITOR", report) # Silver < 70

if __name__ == '__main__':
    unittest.main()
