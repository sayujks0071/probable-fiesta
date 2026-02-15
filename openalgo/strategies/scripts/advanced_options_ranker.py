#!/usr/bin/env python3
import sys
import os
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
import subprocess

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient
from openalgo.strategies.utils.option_analytics import calculate_pcr, calculate_max_pain, calculate_greeks, calculate_iv
from openalgo.strategies.utils.market_data import MarketDataManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "openalgo" / "strategies" / "logs" / "options_ranker.log")
    ]
)
logger = logging.getLogger("AdvancedOptionsRanker")

class AdvancedOptionsRanker:
    def __init__(self, api_key=None, host="http://127.0.0.1:5002"):
        self.api_key = api_key or os.getenv("OPENALGO_API_KEY", "dummy_key")
        self.host = host
        self.client = APIClient(self.api_key, host=self.host)
        self.mdm = MarketDataManager(self.client)

        # Configuration
        self.indices = ["NIFTY", "BANKNIFTY", "SENSEX"]
        self.strategies = [
            "Iron Condor",
            "Credit Spread",
            "Debit Spread",
            "Straddle",
            "Calendar Spread",
            "Gap Fade",
            "Sentiment Reversal"
        ]

        # Script Mapping
        self.script_map = {
            "Iron Condor": "delta_neutral_iron_condor_nifty.py",
            "Gap Fade": "gap_fade_strategy.py",
            "Sentiment Reversal": "sentiment_reversal_strategy.py",
            "Credit Spread": "delta_neutral_iron_condor_nifty.py", # Reusing IC script logic for now or needs new script
            # Others: Placeholder
        }

        # Weights
        self.weights = {
            "iv_rank": 0.25,
            "greeks": 0.20,
            "liquidity": 0.15,
            "pcr_oi": 0.15,
            "vix_regime": 0.10,
            "gift_nifty": 0.10,
            "sentiment": 0.05
        }

    def calculate_iv_rank(self, symbol, current_vix):
        # Simplification: Assume IV follows VIX somewhat.
        # Range 10-30 for indices is typical.
        low = 10
        high = 30
        return max(0, min(100, (current_vix - low) / (high - low) * 100))

    def calculate_composite_score(self, scores):
        composite = 0
        for key, weight in self.weights.items():
            composite += scores.get(key, 0) * weight
        return composite

    def analyze_strategy(self, strategy_type, index, market_data, chain_data):
        vix = market_data.get('vix', 15)
        pcr = calculate_pcr(chain_data)
        sentiment_score, _ = market_data.get('sentiment', (0.5, "Neutral"))
        gift_price, gap_pct = market_data.get('gift_nifty', (0, 0))

        scores = {}
        details = {}

        # 1. IV Rank Score
        # High IV Rank -> Good for Selling (Iron Condor, Credit Spread, Straddle Short)
        # Low IV Rank -> Good for Buying (Debit Spread, Calendar, Gap Fade Long)
        iv_rank = self.calculate_iv_rank(index, vix)
        details['iv_rank'] = round(iv_rank, 1)

        if strategy_type in ["Iron Condor", "Credit Spread", "Straddle"]:
            scores['iv_rank'] = iv_rank
        elif strategy_type in ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]:
            scores['iv_rank'] = 100 - iv_rank
        else:
            scores['iv_rank'] = 50

        # 2. VIX Regime Score
        # Similar to IV Rank but discrete regimes
        vix_score = 50
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             if vix > 20: vix_score = 100
             elif vix < 12: vix_score = 20
             else: vix_score = 70
        elif strategy_type in ["Debit Spread"]:
             if vix < 15: vix_score = 90
             else: vix_score = 30
        scores['vix_regime'] = vix_score

        # 3. Liquidity Score
        # Placeholder: Assume indices are liquid enough, except maybe Sensex
        scores['liquidity'] = 90 if index != "SENSEX" else 70

        # 4. PCR / OI Pattern
        # PCR Reversal Logic: PCR > 1.5 Overbought (Bearish reversal?), PCR < 0.5 Oversold (Bullish?)
        # For Neutral strategies (IC), we want PCR near 1.0
        pcr_score = 50
        if strategy_type == "Iron Condor":
             dist = abs(pcr - 1.0)
             if dist < 0.2: pcr_score = 100
             else: pcr_score = max(0, 100 - dist * 200)
        elif strategy_type == "Sentiment Reversal":
             # Contrarian: High PCR -> Bullish Reversal? Actually High PCR usually means Put Writing (Bullish).
             # Extreme PCR (>1.5) often signals over-bullishness -> Correction?
             # Let's assume Mean Reversion logic.
             if pcr > 1.4 or pcr < 0.6: pcr_score = 90
             else: pcr_score = 40
        scores['pcr_oi'] = pcr_score
        details['pcr'] = pcr

        # 5. Greeks Alignment (Placeholder for complex greek analysis)
        # Assuming we check Delta/Theta
        scores['greeks'] = 60

        # 6. GIFT Nifty Bias
        # Gap Fade: High score if Gap is large
        # IC: High score if Gap is small
        gift_score = 50
        if strategy_type == "Gap Fade":
             if abs(gap_pct) > 0.5: gift_score = 100
             elif abs(gap_pct) > 0.3: gift_score = 70
             else: gift_score = 20
        elif strategy_type == "Iron Condor":
             if abs(gap_pct) < 0.25: gift_score = 100
             elif abs(gap_pct) < 0.5: gift_score = 60
             else: gift_score = 20
        scores['gift_nifty'] = gift_score

        # 7. Sentiment
        # Sentiment Reversal: High score if Sentiment Extreme
        # Neutral strategies: High score if Sentiment Neutral
        sent_score = 50
        if strategy_type == "Sentiment Reversal":
             if sentiment_score > 0.8 or sentiment_score < 0.2: sent_score = 100
             else: sent_score = 20
        elif strategy_type == "Iron Condor":
             if 0.4 <= sentiment_score <= 0.6: sent_score = 100
             else: sent_score = max(0, 100 - abs(sentiment_score - 0.5)*200)
        scores['sentiment'] = sent_score

        # Final Composite
        final_score = self.calculate_composite_score(scores)
        details['score'] = round(final_score, 1)

        # Add context
        details['gap_pct'] = gap_pct
        details['sentiment_score'] = sentiment_score
        details['vix'] = vix

        return details

    def generate_report(self):
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        # Fetch all Data
        vix = self.mdm.get_vix()
        gift_price, gap_pct = self.mdm.get_gift_nifty_gap()
        sent_score, sent_label = self.mdm.get_sentiment()

        market_data = {
            'vix': vix,
            'gift_nifty': (gift_price, gap_pct),
            'sentiment': (sent_score, sent_label)
        }

        print("📈 MARKET DATA SUMMARY:")
        print(f"- NIFTY Spot (Est): {gift_price:.2f} | Gap: {gap_pct:+.2f}%")
        print(f"- India VIX: {vix:.2f}")
        print(f"- News Sentiment: {sent_label} ({sent_score:.2f})")

        opportunities = []

        for index in self.indices:
            chain = self.mdm.get_option_chain(index)
            if not chain:
                continue

            for strat in self.strategies:
                details = self.analyze_strategy(strat, index, market_data, chain)
                details['strategy'] = strat
                details['index'] = index
                opportunities.append(details)

        # Rank
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        top_opportunities = opportunities[:7]

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")
        for i, opp in enumerate(top_opportunities, 1):
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp.get('iv_rank')}% | PCR: {opp.get('pcr')}")
            print(f"   - Context: VIX={opp['vix']:.1f}, Gap={opp['gap_pct']:+.2f}%, Sent={opp['sentiment_score']:.2f}")

            # Warnings
            warnings = []
            if opp['vix'] > 30: warnings.append("High VIX (Reduce Size)")
            if opp['score'] < 60: warnings.append("Low Score")
            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        return top_opportunities

    def deploy_strategies(self, top_strategies):
        """
        Deploy top strategies using subprocess.
        Passes market context via CLI arguments.
        """
        if not top_strategies:
            logger.info("No strategies to deploy.")
            return

        logger.info(f"Deploying {len(top_strategies)} strategies...")
        print("\n🚀 DEPLOYMENT PLAN:")

        for strat in top_strategies:
            # Only deploy if score is reasonable (e.g. > 60)
            if strat['score'] < 60:
                print(f"- Skip: {strat['strategy']} ({strat['index']}) - Score {strat['score']} < 60")
                continue

            script_name = self.script_map.get(strat['strategy'])
            if not script_name:
                logger.warning(f"No script mapped for {strat['strategy']}")
                continue

            script_path = project_root / "openalgo" / "strategies" / "scripts" / script_name
            if not script_path.exists():
                logger.error(f"Script not found: {script_path}")
                continue

            cmd = [
                sys.executable, str(script_path),
                "--symbol", strat['index'],
                "--port", str(5002), # Default options port
                "--vix", str(strat['vix']),
                "--sentiment_score", str(strat['sentiment_score']),
                "--gap_pct", str(strat['gap_pct'])
            ]

            logger.info(f"Executing: {' '.join(cmd)}")
            print(f"- Deploying: {strat['strategy']} on {strat['index']} (Score: {strat['score']})")

            try:
                # Run detached
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"Deployment failed for {strat['strategy']}: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", action="store_true", help="Deploy top strategies")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    ranker = AdvancedOptionsRanker(host=f"http://127.0.0.1:{args.port}")
    top_strats = ranker.generate_report()

    if args.deploy:
        ranker.deploy_strategies(top_strats)

if __name__ == "__main__":
    main()
