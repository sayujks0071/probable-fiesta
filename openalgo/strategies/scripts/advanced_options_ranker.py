#!/usr/bin/env python3
import sys
import os
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
import math
import subprocess

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient
from openalgo.strategies.utils.option_analytics import calculate_pcr
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
        self.market_mgr = MarketDataManager(self.client)

        # Configuration
        self.indices = ["NIFTY", "BANKNIFTY", "SENSEX"]
        self.strategies = ["Iron Condor", "Credit Spread", "Debit Spread", "Straddle", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]

        # Script Mapping
        self.script_map = {
            "Iron Condor": "delta_neutral_iron_condor_nifty.py",
            "Gap Fade": "gap_fade_strategy.py",
            "Sentiment Reversal": "sentiment_reversal_strategy.py"
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

    def fetch_market_data(self):
        logger.info("Fetching market data...")
        data = {}

        # Use MarketDataManager
        data['vix'] = self.market_mgr.get_vix()
        spot, gap_pct = self.market_mgr.get_nifty_gap()
        data['nifty_spot'] = spot
        data['gap_pct'] = gap_pct

        score, label = self.market_mgr.get_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        data['chains'] = {}
        for index in self.indices:
            try:
                exchange = "NFO" if index != "SENSEX" else "BFO"
                chain = self.client.get_option_chain(index, exchange)
                if chain:
                    data['chains'][index] = chain
            except Exception as e:
                logger.error(f"Failed to fetch chain for {index}: {e}")

        return data

    def calculate_iv_rank(self, symbol, current_iv):
        # Simplification: Assume IV Range 10-30 for indices
        low = 10
        high = 30
        return max(0, min(100, (current_iv - low) / (high - low) * 100))

    def calculate_composite_score(self, scores):
        """
        Calculate final weighted score.
        scores: dict with keys matching weights
        """
        composite = 0
        for key, weight in self.weights.items():
            composite += scores.get(key, 0) * weight
        return composite

    def analyze_strategy(self, strategy_type, index, market_data, chain_data):
        """
        Score a specific strategy for an index using multi-factor analysis.
        """
        vix = market_data.get('vix', 15)
        pcr = calculate_pcr(chain_data)
        sentiment = market_data.get('sentiment_score', 0.5)
        gap = market_data.get('gap_pct', 0)

        scores = {}
        details = {}

        # 1. IV Rank
        iv_rank = self.calculate_iv_rank(index, vix)
        details['iv_rank'] = iv_rank

        if strategy_type in ["Iron Condor", "Credit Spread", "Straddle"]:
            scores['iv_rank'] = iv_rank
        elif strategy_type in ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]:
            scores['iv_rank'] = 100 - iv_rank

        # 2. VIX Regime
        vix_score = 50
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             if vix > 20: vix_score = 100
             elif vix < 12: vix_score = 20
             else: vix_score = 60
        elif strategy_type in ["Calendar Spread"]:
             if vix < 13: vix_score = 90
             elif vix > 20: vix_score = 10
        elif strategy_type in ["Debit Spread"]:
             if vix < 15: vix_score = 80
             else: vix_score = 40
        scores['vix_regime'] = vix_score

        # 3. Liquidity
        scores['liquidity'] = 90

        # 4. PCR / OI
        pcr_score = 50
        if strategy_type == "Iron Condor":
             dist_from_1 = abs(pcr - 1.0)
             if dist_from_1 < 0.2: pcr_score = 90
             else: pcr_score = max(0, 100 - dist_from_1 * 100)

        scores['pcr_oi'] = pcr_score
        details['pcr'] = pcr

        # 5. Greeks Alignment
        greeks_score = 50
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             if vix > 18: greeks_score += 20
             if vix > 25: greeks_score += 10
        scores['greeks'] = greeks_score

        # 6. GIFT Nifty Bias
        gift_score = 50
        if strategy_type == "Gap Fade":
             if abs(gap) > 0.5: gift_score = 100
             elif abs(gap) > 0.3: gift_score = 70
             else: gift_score = 20
        elif strategy_type == "Iron Condor":
             if abs(gap) < 0.2: gift_score = 100
             else: gift_score = max(0, 100 - abs(gap)*200)

        scores['gift_nifty'] = gift_score

        # 7. Sentiment
        sent_score = 50
        if strategy_type == "Sentiment Reversal":
             dist = abs(sentiment - 0.5)
             if dist > 0.3: sent_score = 90
             else: sent_score = 20
        elif strategy_type == "Iron Condor":
             dist = abs(sentiment - 0.5)
             if dist < 0.1: sent_score = 100
             else: sent_score = max(0, 100 - dist * 200)

        scores['sentiment'] = sent_score

        # Calculate Final
        final_score = self.calculate_composite_score(scores)
        details['score'] = round(final_score, 1)
        details['gap_pct'] = gap
        details['sentiment_val'] = sentiment

        return details

    def generate_report(self):
        """Main execution flow."""
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        market_data = self.fetch_market_data()

        print("📈 MARKET DATA SUMMARY:")
        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 12 else "Medium")
        print(f"- India VIX: {vix} ({vix_label})")
        print(f"- Nifty Gap (Est): {market_data.get('gap_pct'):.2f}%")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} (Score: {market_data.get('sentiment_score'):.2f})")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        opportunities = []

        for index in self.indices:
            chain = market_data['chains'].get(index)
            if not chain:
                continue

            for strategy in self.strategies:
                details = self.analyze_strategy(strategy, index, market_data, chain)
                details['strategy'] = strategy
                details['index'] = index
                details['sentiment_score'] = market_data.get('sentiment_score', 0.5)
                details['gap_pct'] = market_data.get('gap_pct', 0.0)
                opportunities.append(details)

        # Rank by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        for i, opp in enumerate(opportunities[:5], 1):
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp.get('iv_rank', 0):.1f}% | PCR: {opp.get('pcr', 0)}")
            print(f"   - Rationale: Multi-factor score (VIX, Greeks, Sentiment, Gap)")

            # Risk Warning Checks
            warnings = []
            if market_data['vix'] > 30: warnings.append("High VIX - Reduce Size")
            if opp['score'] < 60: warnings.append("Low Score - Caution")
            if opp['index'] == "NIFTY" and abs(opp.get('gap_pct', 0)) > 0.8: warnings.append("Large Gap - Volatility Risk")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- [All]: Added Composite Scoring (IV, Greeks, Liquidity, PCR, VIX, Gap, Sentiment)")
        print("- [Iron Condor]: VIX & Sentiment Filters, Gap adjustments")
        print("- [Gap Fade]: Gap Threshold Filters")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- Gap Fade Strategy: Targets reversal of overnight gaps > 0.5%")
        print("- Sentiment Reversal: Targets mean reversion on extreme sentiment")

        print("\n🚀 DEPLOYMENT PLAN:")
        to_deploy = [opp for opp in opportunities if opp['score'] >= 70][:3]
        if to_deploy:
             print(f"- Deploy: {', '.join([f'{x['strategy']} ({x['index']})' for x in to_deploy])}")
             return to_deploy
        else:
             print("- Deploy: None (No strategy met score threshold > 70)")
             return []

    def deploy_strategies(self, top_strategies):
        """Deploy top strategies."""
        logger.info(f"Deploying {len(top_strategies)} top strategies...")

        for strat in top_strategies:
            strategy_name = strat['strategy']
            script = self.script_map.get(strategy_name)

            if not script:
                logger.warning(f"No script mapped for strategy '{strategy_name}'. Skipping deployment.")
                continue

            script_path = project_root / "openalgo" / "strategies" / "scripts" / script
            if not script_path.exists():
                logger.warning(f"Script file {script_path} not found.")
                continue

            cmd = [sys.executable, str(script_path), "--symbol", strat['index'], "--port", str(self.host.split(':')[-1])]

            # Pass extra args
            cmd.extend(["--sentiment_score", str(strat.get('sentiment_score', 0.5))])
            cmd.extend(["--gap_pct", str(strat.get('gap_pct', 0.0))])

            logger.info(f"Executing: {' '.join(cmd)}")

            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"✅ Deployed: {strategy_name} on {strat['index']}")
            except Exception as e:
                logger.error(f"Failed to deploy {strategy_name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Advanced Options Ranker")
    parser.add_argument("--deploy", action="store_true", help="Deploy top strategies")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    ranker = AdvancedOptionsRanker(host=f"http://127.0.0.1:{args.port}")
    top_strats = ranker.generate_report()

    if args.deploy and top_strats:
        ranker.deploy_strategies(top_strats)

if __name__ == "__main__":
    main()
