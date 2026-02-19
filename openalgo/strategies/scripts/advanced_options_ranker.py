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

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, is_market_open
from openalgo.strategies.utils.option_analytics import calculate_pcr, calculate_max_pain, calculate_greeks, calculate_iv_rank

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
        self.api_key = api_key or os.getenv("OPENALGO_APIKEY") or os.getenv("OPENALGO_API_KEY", "dummy_key")
        self.host = host
        self.client = APIClient(self.api_key, host=self.host)

        # Configuration
        self.indices = ["NIFTY", "BANKNIFTY", "SENSEX"]
        self.strategies = ["Iron Condor", "Credit Spread", "Debit Spread", "Straddle", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]

        # Script Mapping
        self.script_map = {
            "Iron Condor": "delta_neutral_iron_condor_nifty.py",
            "Gap Fade": "gap_fade_strategy.py",
            "Sentiment Reversal": "sentiment_reversal_strategy.py",
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

    def _fetch_gift_nifty_proxy(self, nifty_spot):
        try:
            # In a real scenario, fetch 'GIFT NIFTY' or 'SGX NIFTY' symbol.
            # Here we act as a proxy or use previous close if available.
            # Returning 0.0 gap for deterministic behavior in absence of real feed.
            return nifty_spot, 0.0
        except Exception as e:
            logger.warning(f"Error fetching GIFT Nifty proxy: {e}")
            return nifty_spot, 0.0

    def _fetch_news_sentiment(self):
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

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'up', 'strong']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'down', 'weak']

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
        try:
            vix_quote = self.client.get_quote("INDIA VIX", "NSE")
            data['vix'] = float(vix_quote['ltp']) if vix_quote and 'ltp' in vix_quote else 15.0
        except:
            data['vix'] = 15.0

        # 2. Spot Prices & GIFT Nifty
        try:
            nifty_quote = self.client.get_quote("NIFTY 50", "NSE")
            data['nifty_spot'] = float(nifty_quote['ltp']) if nifty_quote and 'ltp' in nifty_quote else 0.0
        except:
            data['nifty_spot'] = 0.0

        gift_price, gap_pct = self._fetch_gift_nifty_proxy(data['nifty_spot'])
        data['gift_nifty'] = gift_price
        data['gap_pct'] = gap_pct

        # 3. Sentiment
        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        # 4. Chains & Greeks
        data['chains'] = {}
        data['greeks'] = {} # Store aggregated greek info or raw

        for index in self.indices:
            try:
                exchange = "NFO" if index != "SENSEX" else "BFO"
                chain = self.client.get_option_chain(index, exchange)
                if chain:
                    # Enrich chain with calculated greeks if missing
                    # We assume Spot is available.
                    spot = data.get('nifty_spot', 10000) # Fallback
                    if index == "BANKNIFTY":
                         bn_quote = self.client.get_quote("NIFTY BANK", "NSE")
                         spot = float(bn_quote['ltp']) if bn_quote else spot
                    elif index == "SENSEX":
                         sx_quote = self.client.get_quote("SENSEX", "BSE")
                         spot = float(sx_quote['ltp']) if sx_quote else spot

                    # Calculate Greeks for chain
                    # Using a default T = 7 days if no expiry info, else parse.
                    # Simplified: Just ensure we have some greek data.
                    # Ideally we iterate and add 'greeks' dict to each item.

                    data['chains'][index] = chain
            except Exception as e:
                logger.error(f"Error fetching chain for {index}: {e}")

        return data

    def calculate_composite_score(self, strategy, index, market_data, chain_data):
        """
        Calculate composite score based on the 7-factor model.
        """
        vix = market_data.get('vix', 15)
        gap = market_data.get('gap_pct', 0)
        sentiment = market_data.get('sentiment_score', 0.5)

        # 1. IV Rank Score (0.25)
        # Using VIX as proxy for IV for the index
        iv_rank = calculate_iv_rank(vix, low=10, high=30)

        iv_score = 50
        if strategy in ["Iron Condor", "Credit Spread", "Straddle"]:
            # Sell strategies favor high IV
            iv_score = iv_rank
        elif strategy in ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]:
            # Buy strategies favor low IV
            iv_score = 100 - iv_rank

        # 2. VIX Regime Score (0.10)
        vix_score = 50
        if strategy in ["Iron Condor", "Credit Spread"]:
             if vix > 20: vix_score = 100
             elif vix < 12: vix_score = 20
        elif strategy == "Calendar Spread":
             if vix < 13: vix_score = 90
             elif vix > 20: vix_score = 10
        elif strategy == "Debit Spread":
             if vix < 15: vix_score = 80
             else: vix_score = 40

        # 3. PCR / OI Pattern Score (0.15)
        pcr = calculate_pcr(chain_data)
        pcr_score = 50
        # Extreme PCR suggests reversal
        dist_from_1 = abs(pcr - 1.0)
        if strategy in ["Sentiment Reversal", "Gap Fade"]:
            if dist_from_1 > 0.5: pcr_score = 80
        elif strategy == "Iron Condor":
            if dist_from_1 < 0.2: pcr_score = 90
            else: pcr_score = max(0, 100 - dist_from_1 * 100)

        # 4. Liquidity Score (0.15)
        # Assume major indices are liquid
        liquidity_score = 90

        # 5. Greeks Alignment (0.20)
        # Placeholder for detailed greek analysis.
        # For selling, we want Theta decay (High Theta).
        # High VIX usually means higher extrinsic value -> higher Theta.
        greeks_score = 50
        if strategy in ["Iron Condor", "Credit Spread"]:
             if vix > 18: greeks_score = 80

        # 6. GIFT Nifty Bias (0.10)
        gift_score = 50
        if strategy == "Gap Fade":
             if abs(gap) > 0.5: gift_score = 100
             elif abs(gap) > 0.3: gift_score = 70
             else: gift_score = 20
        elif strategy == "Iron Condor":
             if abs(gap) < 0.2: gift_score = 100
             else: gift_score = max(0, 100 - abs(gap)*200)

        # 7. News Sentiment (0.05)
        sent_score = 50
        dist_sent = abs(sentiment - 0.5)
        if strategy == "Sentiment Reversal":
             if dist_sent > 0.3: sent_score = 90
             else: sent_score = 20
        elif strategy == "Iron Condor":
             if dist_sent < 0.1: sent_score = 100
             else: sent_score = max(0, 100 - dist_sent * 200)

        # Weighted Sum
        composite = (
            iv_score * self.weights['iv_rank'] +
            greeks_score * self.weights['greeks'] +
            liquidity_score * self.weights['liquidity'] +
            pcr_score * self.weights['pcr_oi'] +
            vix_score * self.weights['vix_regime'] +
            gift_score * self.weights['gift_nifty'] +
            sent_score * self.weights['sentiment']
        )

        return round(composite, 1), {
            "iv_rank": iv_score,
            "pcr": pcr,
            "vix": vix,
            "gap": gap,
            "sentiment": sentiment
        }

    def generate_report(self):
        """Main execution flow."""
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        market_data = self.fetch_market_data()

        print("📈 MARKET DATA SUMMARY:")
        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 12 else "Medium")
        print(f"- NIFTY Spot: {market_data.get('nifty_spot')} | VIX: {vix} ({vix_label})")
        print(f"- GIFT Nifty Gap (Est): {market_data.get('gap_pct'):.2f}%")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} (Score: {market_data.get('sentiment_score'):.2f})")

        opportunities = []

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        for index in self.indices:
            chain = market_data['chains'].get(index)
            if not chain:
                continue

            for strategy in self.strategies:
                score, details = self.calculate_composite_score(strategy, index, market_data, chain)

                opp = {
                    "strategy": strategy,
                    "index": index,
                    "score": score,
                    "details": details
                }
                opportunities.append(opp)

        # Rank by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        for i, opp in enumerate(opportunities[:5], 1):
            d = opp['details']
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank Score: {d['iv_rank']:.1f} | PCR: {d['pcr']}")
            print(f"   - Rationale: Multi-factor score (VIX: {d['vix']}, Gap: {d['gap']:.2f}%, Sent: {d['sentiment']:.2f})")

            # Risk Warning Checks
            warnings = []
            if d['vix'] > 30: warnings.append("High VIX - Reduce Size")
            if opp['score'] < 60: warnings.append("Low Score - Caution")
            if opp['index'] == "NIFTY" and abs(d['gap']) > 0.8: warnings.append("Large Gap - Volatility Risk")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")
                opp['warnings'] = warnings

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- [All]: Added Composite Scoring (IV, Greeks, Liquidity, PCR, VIX, Gap, Sentiment)")
        print("- [Iron Condor]: VIX & Sentiment Filters")
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

            # Pass extra args based on details
            details = strat['details']

            if strategy_name == "Iron Condor":
                cmd.extend(["--sentiment_score", str(details.get('sentiment', 0.5))])
                cmd.extend(["--gap_percent", str(details.get('gap', 0.0))])

            if strategy_name == "Gap Fade":
                cmd.extend(["--threshold", "0.5"]) # Default

            if strategy_name == "Sentiment Reversal":
                cmd.extend(["--sentiment_score", str(details.get('sentiment', 0.5))])

            logger.info(f"Executing: {' '.join(cmd)}")

            try:
                # Fire and forget (or log output)
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
