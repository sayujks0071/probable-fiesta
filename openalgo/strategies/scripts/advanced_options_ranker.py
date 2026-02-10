#!/usr/bin/env python3
import sys
import os
import json
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re
import math
import subprocess
import pandas as pd
import numpy as np

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, is_market_open
from openalgo.strategies.utils.option_analytics import calculate_pcr, calculate_max_pain, calculate_greeks, calculate_iv

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
            # Add others as they are implemented
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

    def _fetch_gift_nifty_proxy(self):
        """
        Estimate GIFT Nifty gap using NIFTY 50 Futures Open vs Previous Close if available.
        Or use a mock/proxy.
        Ideally, fetch 'GIFT NIFTY' or SGX Nifty if available in instruments.
        """
        try:
            # Try to get NIFTY 50 Futures
            # Assuming current month future
            # This is complex to resolve dynamically without instrument master lookup for expiry
            # Simplification: Use NIFTY 50 Spot Previous Close vs Open if market just opened
            # Or use NIFTY 50 Spot vs NIFTY 50 Future

            # For now, we return 0.0 gap unless we can reliably fetch external data
            # Enhancements: Scrape or use specific symbol if available
            return 0.0 # Placeholder
        except Exception as e:
            logger.warning(f"Error fetching GIFT Nifty proxy: {e}")
            return 0.0

    def _fetch_news_sentiment(self):
        """Scrape Economic Times RSS for sentiment"""
        try:
            url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
            try:
                response = requests.get(url, timeout=5)
            except:
                return 0.5, "Neutral"

            if response.status_code != 200:
                return 0.5, "Neutral"

            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'up']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'down']

            score = 0
            count = 0
            for item in items[:15]:
                title = item.title.text.lower()
                p_count = sum(1 for w in positive_words if w in title)
                n_count = sum(1 for w in negative_words if w in title)
                if p_count > n_count: score += 1
                elif n_count > p_count: score -= 1
                count += 1

            if count == 0: return 0.5, "Neutral"

            # Normalize to 0-1
            # Range of score is -count to +count
            # (score + count) / (2 * count)
            normalized_score = (score + count) / (2 * count)
            normalized_score = max(0.0, min(1.0, normalized_score))

            label = "Neutral"
            if normalized_score > 0.6: label = "Positive"
            elif normalized_score < 0.4: label = "Negative"

            return normalized_score, label

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return 0.5, "Neutral"

    def fetch_market_data(self):
        logger.info("Fetching market data...")
        data = {}

        # 1. VIX
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        data['vix'] = float(vix_quote['ltp']) if vix_quote and 'ltp' in vix_quote else 15.0

        # 2. VIX History for IV Rank
        # Fetch 1 year of daily data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        vix_hist = self.client.history("INDIA VIX", "NSE", interval="day",
                                     start_date=start_date.strftime("%Y-%m-%d"),
                                     end_date=end_date.strftime("%Y-%m-%d"))

        data['vix_history'] = vix_hist

        # 3. Indices Spot & Chain
        data['chains'] = {}
        data['spots'] = {}

        for index in self.indices:
            # Spot
            exchange = "NSE" if index == "NIFTY" or index == "BANKNIFTY" else "BSE" # SENSEX on BSE usually
            # But options are on NFO/BFO
            # Kite symbol for NIFTY is NIFTY 50 usually, BANKNIFTY is NIFTY BANK
            # APIClient might mock or map it.
            # Assuming "NIFTY" maps to "NIFTY 50" inside client or we pass "NIFTY 50"

            search_symbol = index
            if index == "NIFTY": search_symbol = "NIFTY 50"
            if index == "BANKNIFTY": search_symbol = "NIFTY BANK"

            spot_quote = self.client.get_quote(search_symbol, exchange)
            spot = float(spot_quote['ltp']) if spot_quote and 'ltp' in spot_quote else 0.0
            data['spots'][index] = spot

            # Chain
            opt_exchange = "NFO" if index != "SENSEX" else "BFO"
            chain = self.client.get_option_chain(index, opt_exchange)
            if chain:
                data['chains'][index] = chain

        # 4. Sentiment & Gap
        data['gap_pct'] = self._fetch_gift_nifty_proxy()
        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        return data

    def calculate_iv_rank(self, current_iv, history_df):
        """
        Calculate IV Rank based on VIX history as proxy if stock IV not available.
        IV Rank = (Current - Min) / (Max - Min) * 100
        """
        if history_df is None or history_df.empty:
            return 50.0 # Default

        try:
            # Use 'close' of VIX history
            high = history_df['close'].max()
            low = history_df['close'].min()

            if high == low: return 50.0

            rank = ((current_iv - low) / (high - low)) * 100
            return max(0.0, min(100.0, rank))
        except Exception as e:
            logger.error(f"Error calculating IV Rank: {e}")
            return 50.0

    def calculate_composite_score(self, scores):
        """
        Calculate final weighted score.
        scores: dict with keys matching weights
        """
        composite = 0
        for key, weight in self.weights.items():
            composite += scores.get(key, 0) * weight
        return composite

    def analyze_strategy(self, strategy_type, index, market_data):
        """
        Score a specific strategy for an index using multi-factor analysis.
        """
        vix = market_data.get('vix', 15)
        spot = market_data['spots'].get(index, 0)
        chain_data = market_data['chains'].get(index, [])
        vix_hist = market_data.get('vix_history')

        if not chain_data or spot == 0:
            return None

        pcr = calculate_pcr(chain_data)
        sentiment = market_data.get('sentiment_score', 0.5)
        gap = market_data.get('gap_pct', 0)

        scores = {}
        details = {}

        # 1. IV Rank (Using VIX as proxy for Index IV)
        iv_rank = self.calculate_iv_rank(vix, vix_hist)
        details['iv_rank'] = iv_rank
        details['vix'] = vix

        # Scoring Logic based on Strategy Type
        # Selling Strategies prefer High IV Rank
        # Buying Strategies prefer Low IV Rank

        selling_strategies = ["Iron Condor", "Credit Spread", "Straddle", "Strangle"]
        buying_strategies = ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"] # Gap Fade usually buying options

        if strategy_type in selling_strategies:
            scores['iv_rank'] = iv_rank
        else:
            scores['iv_rank'] = 100 - iv_rank

        # 2. VIX Regime
        # High VIX (>20) -> Sell
        # Low VIX (<12) -> Buy
        vix_score = 50
        if strategy_type in selling_strategies:
             if vix > 20: vix_score = 100
             elif vix < 12: vix_score = 10
             else: vix_score = 60 + (vix - 12) * 2
        elif strategy_type in buying_strategies:
             if vix < 15: vix_score = 90
             elif vix > 25: vix_score = 10
             else: vix_score = 50

        scores['vix_regime'] = vix_score

        # 3. Liquidity
        # Check OI of ATM strikes
        # Simplification: Assume major indices have liquidity, score high
        scores['liquidity'] = 90

        # 4. PCR / OI Pattern
        # PCR > 1.5 -> Oversold (Bullish Reversal possibility) -> Good for Bull Put Spread / Call Buy
        # PCR < 0.6 -> Overbought (Bearish Reversal) -> Good for Bear Call Spread / Put Buy
        # Neutral strategies prefer PCR around 1.0

        pcr_score = 50
        if strategy_type == "Iron Condor" or strategy_type == "Straddle":
             dist = abs(pcr - 1.0)
             if dist < 0.2: pcr_score = 90
             else: pcr_score = max(0, 100 - dist * 100)
        elif "Credit Spread" in strategy_type:
            # Need to know if Bull or Bear. Strategy name is generic here.
            # Assuming neutral bias for generic credit spread, similar to IC
            pcr_score = 50

        scores['pcr_oi'] = pcr_score
        details['pcr'] = pcr

        # 5. Greeks Alignment
        # VIX check again? Or Delta check?
        # If Iron Condor, we want Delta Neutrality available.
        # We can check if we can find strikes with Delta ~0.20
        # For now, simplistic score based on VIX stability for Greeks
        greeks_score = 50
        if strategy_type == "Iron Condor":
             # Best when VIX is stable or falling
             # Hard to predict VIX trend without more data
             if 12 <= vix <= 25: greeks_score = 80
             else: greeks_score = 40
        scores['greeks'] = greeks_score

        # 6. GIFT Nifty / Gap
        # Gap Fade specifics
        gift_score = 50
        if strategy_type == "Gap Fade":
             if abs(gap) > 0.5: gift_score = 100
             elif abs(gap) > 0.3: gift_score = 70
             else: gift_score = 10
        elif strategy_type == "Iron Condor":
             # Hate gaps
             if abs(gap) < 0.2: gift_score = 100
             else: gift_score = 20

        scores['gift_nifty'] = gift_score
        details['gap_pct'] = gap

        # 7. Sentiment
        # Sentiment Reversal: Buy when extreme
        sent_score = 50
        if strategy_type == "Sentiment Reversal":
             dist = abs(sentiment - 0.5)
             if dist > 0.3: sent_score = 95 # Extreme sentiment
             else: sent_score = 20
        elif strategy_type in selling_strategies:
             # Prefer neutral sentiment
             dist = abs(sentiment - 0.5)
             if dist < 0.1: sent_score = 100
             else: sent_score = max(0, 100 - dist * 200)

        scores['sentiment'] = sent_score
        details['sentiment_val'] = sentiment

        # Final Score
        final_score = self.calculate_composite_score(scores)
        details['score'] = round(final_score, 1)

        return details

    def generate_report(self):
        """Main execution flow."""
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        market_data = self.fetch_market_data()

        print("📈 MARKET DATA SUMMARY:")
        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 12 else "Medium")
        print(f"- India VIX: {vix} ({vix_label})")

        if market_data.get('vix_history') is not None:
             print(f"- VIX Rank: {self.calculate_iv_rank(vix, market_data['vix_history']):.1f}%")

        print(f"- GIFT Nifty Gap (Est): {market_data.get('gap_pct'):.2f}%")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} (Score: {market_data.get('sentiment_score'):.2f})")

        for idx, spot in market_data['spots'].items():
             print(f"- {idx} Spot: {spot}")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        opportunities = []

        for index in self.indices:
            if index not in market_data['chains']:
                continue

            for strategy in self.strategies:
                details = self.analyze_strategy(strategy, index, market_data)
                if details:
                    details['strategy'] = strategy
                    details['index'] = index
                    opportunities.append(details)

        # Rank by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        for i, opp in enumerate(opportunities[:7], 1):
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp.get('iv_rank', 0):.1f}% | PCR: {opp.get('pcr', 0)}")
            print(f"   - Filters: VIX={opp.get('vix', 0):.1f}, Gap={opp.get('gap_pct', 0):.2f}%, Sent={opp.get('sentiment_val', 0.5):.2f}")

            # Risk Warnings
            warnings = []
            if opp['vix'] > 30: warnings.append("Extreme VIX (Reduce Size)")
            if opp['score'] < 60: warnings.append("Low Confidence")
            if opp.get('pcr') > 1.6 or opp.get('pcr') < 0.5: warnings.append("Extreme PCR")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        print("\n🚀 DEPLOYMENT PLAN:")
        # Deploy logic: Score > 70
        to_deploy = [opp for opp in opportunities if opp['score'] >= 70]

        if not to_deploy:
             print("- No strategies met the threshold (>70).")
             return []

        unique_deploy = []
        seen = set()
        for d in to_deploy:
             key = f"{d['strategy']}_{d['index']}"
             if key not in seen:
                  unique_deploy.append(d)
                  seen.add(key)

        # Limit to top 3
        unique_deploy = unique_deploy[:3]

        for d in unique_deploy:
             print(f"- Deploying: {d['strategy']} on {d['index']}")

        return unique_deploy

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

            # Construct command
            cmd = [sys.executable, str(script_path), "--symbol", strat['index'], "--port", str(5002)]

            # Pass extra args
            if strategy_name == "Iron Condor":
                cmd.extend(["--sentiment_score", str(strat.get('sentiment_val', 0.5))])
            if strategy_name == "Gap Fade":
                # Maybe pass gap threshold or just run it (it checks gap itself)
                pass

            logger.info(f"Executing: {' '.join(cmd)}")
            print(f"✅ Triggered: {strategy_name} on {strat['index']}")

            try:
                # Run as subprocess
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
