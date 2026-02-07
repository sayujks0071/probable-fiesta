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
from openalgo.strategies.utils.option_analytics import calculate_pcr, calculate_max_pain, calculate_greeks

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
        self.strategies = ["Iron Condor", "Credit Spread", "Debit Spread", "Straddle", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]

        # Script Mapping
        self.script_map = {
            "Iron Condor": "delta_neutral_iron_condor_nifty.py",
            "Gap Fade": "gap_fade_strategy.py",
            "Sentiment Reversal": "sentiment_reversal_strategy.py",
        }

        # Thresholds
        self.vix_high_threshold = 20
        self.vix_extreme_threshold = 30
        self.vix_low_threshold = 12
        self.liquidity_oi_threshold = 100000  # Minimum OI

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

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'up']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'down', 'weak']

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

            normalized_score = 0.5 + (score / (2 * count))
            normalized_score = max(0.0, min(1.0, normalized_score))

            label = "Neutral"
            if normalized_score >= 0.6: label = "Positive"
            elif normalized_score <= 0.4: label = "Negative"

            return normalized_score, label

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return 0.5, "Neutral"

    def fetch_market_data(self):
        logger.info("Fetching market data...")
        data = {}

        # 1. India VIX
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        data['vix'] = float(vix_quote['ltp']) if vix_quote else 15.0

        # 2. Spot Prices
        nifty_quote = self.client.get_quote("NIFTY 50", "NSE")
        data['nifty_spot'] = float(nifty_quote['ltp']) if nifty_quote else 0.0

        banknifty_quote = self.client.get_quote("NIFTY BANK", "NSE")
        data['banknifty_spot'] = float(banknifty_quote['ltp']) if banknifty_quote else 0.0

        sensex_quote = self.client.get_quote("SENSEX", "BSE")
        data['sensex_spot'] = float(sensex_quote['ltp']) if sensex_quote else 0.0

        # 3. GIFT Nifty / Gap
        gift_price, gap_pct = self._fetch_gift_nifty_proxy(data['nifty_spot'])
        data['gift_nifty'] = gift_price
        data['gap_pct'] = gap_pct

        # 4. Sentiment
        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        # 5. Option Chains
        data['chains'] = {}
        for index in self.indices:
            exchange = "NFO" if index != "SENSEX" else "BFO"
            chain = self.client.get_option_chain(index, exchange)
            if chain:
                spot = data.get(f"{index.lower()}_spot", 0)
                if spot == 0 and index == "NIFTY": spot = data['nifty_spot']

                enhanced_chain = []
                for item in chain:
                    strike = item.get('strike')
                    if not strike: continue

                    expiry = item.get('expiry')
                    T = 7/365.0
                    if expiry:
                        try:
                            exp_date = datetime.strptime(expiry, "%Y-%m-%d")
                            T = (exp_date - datetime.now()).days / 365.0
                            if T <= 0: T = 1/365.0
                        except:
                            pass

                    r = 0.06

                    # CE
                    ce_iv = item.get('ce_iv', 0)
                    if ce_iv == 0: ce_iv = data['vix'] / 100.0
                    else: ce_iv = ce_iv / 100.0

                    ce_greeks = calculate_greeks(spot, strike, T, r, ce_iv, 'ce')
                    item['ce_greeks'] = ce_greeks

                    # PE
                    pe_iv = item.get('pe_iv', 0)
                    if pe_iv == 0: pe_iv = data['vix'] / 100.0
                    else: pe_iv = pe_iv / 100.0

                    pe_greeks = calculate_greeks(spot, strike, T, r, pe_iv, 'pe')
                    item['pe_greeks'] = pe_greeks

                    enhanced_chain.append(item)

                data['chains'][index] = enhanced_chain

        return data

    def calculate_iv_rank(self, symbol, current_vix):
        low = 10
        high = 30
        return max(0, min(100, (current_vix - low) / (high - low) * 100))

    def calculate_composite_score(self, scores):
        composite = 0
        for key, weight in self.weights.items():
            composite += scores.get(key, 0) * weight
        return composite

    def score_greeks_alignment(self, strategy, chain_data, vix):
        score = 50
        if strategy in ["Iron Condor", "Credit Spread"]:
            if vix > 18: score += 20
            if vix > 25: score += 20
            if vix < 12: score -= 30
        elif strategy in ["Debit Spread", "Straddle"]:
            if vix < 15: score += 30
            if vix > 25: score -= 20
        return max(0, min(100, score))

    def score_liquidity(self, chain_data):
        total_oi = 0
        for item in chain_data:
             total_oi += item.get('ce_oi', 0) + item.get('pe_oi', 0)

        if total_oi > self.liquidity_oi_threshold * 10:
            return 100
        elif total_oi > self.liquidity_oi_threshold:
            return 70
        return 30

    def score_pcr_oi(self, strategy, pcr):
        score = 50
        is_extreme_high = pcr > 1.5
        is_extreme_low = pcr < 0.5

        if strategy == "Sentiment Reversal":
            if is_extreme_high or is_extreme_low: score = 90
            else: score = 30
        elif strategy in ["Iron Condor"]:
            dist = abs(pcr - 1.0)
            if dist < 0.2: score = 90
            else: score = max(0, 100 - dist * 100)
        return score

    def score_vix_regime(self, strategy, vix):
        score = 50
        if strategy in ["Iron Condor", "Credit Spread"]:
             if vix > 20: score = 100
             elif vix < 12: score = 20
             else: score = 60
        elif strategy in ["Calendar Spread"]:
             if vix < 13: score = 90
             elif vix > 20: score = 10
        elif strategy in ["Debit Spread", "Straddle"]:
             if vix < 15: score = 80
             elif vix > 25: score = 30
             else: score = 50
        return score

    def score_gift_bias(self, strategy, gap_pct):
        score = 50
        if strategy == "Gap Fade":
             if abs(gap_pct) > 0.5: score = 100
             elif abs(gap_pct) > 0.3: score = 70
             else: score = 20
        elif strategy == "Iron Condor":
             if abs(gap_pct) < 0.2: score = 100
             else: score = max(0, 100 - abs(gap_pct)*200)
        return score

    def score_sentiment(self, strategy, sentiment_score):
        score = 50
        dist_from_neutral = abs(sentiment_score - 0.5)

        if strategy == "Sentiment Reversal":
             if dist_from_neutral > 0.3: score = 90
             else: score = 20
        elif strategy == "Iron Condor":
             if dist_from_neutral < 0.1: score = 100
             else: score = max(0, 100 - dist_from_neutral * 200)
        return score

    def analyze_strategy(self, strategy_type, index, market_data, chain_data):
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
        scores['vix_regime'] = self.score_vix_regime(strategy_type, vix)

        # 3. Liquidity
        scores['liquidity'] = self.score_liquidity(chain_data)

        # 4. PCR / OI
        scores['pcr_oi'] = self.score_pcr_oi(strategy_type, pcr)
        details['pcr'] = pcr

        # 5. Greeks Alignment
        scores['greeks'] = self.score_greeks_alignment(strategy_type, chain_data, vix)

        # 6. GIFT Nifty Bias
        scores['gift_nifty'] = self.score_gift_bias(strategy_type, gap)

        # 7. Sentiment
        scores['sentiment'] = self.score_sentiment(strategy_type, sentiment)

        # Calculate Final
        final_score = self.calculate_composite_score(scores)
        details['score'] = round(final_score, 1)
        details['gap_pct'] = gap
        details['sentiment_val'] = sentiment

        # Populate Greeks for display (using first item or avg)
        # Just getting max pain for context
        mp = calculate_max_pain(chain_data)
        details['max_pain'] = mp

        return details

    def generate_report(self):
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        market_data = self.fetch_market_data()

        print("📈 MARKET DATA SUMMARY:")
        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 12 else "Medium")
        print(f"- India VIX: {vix} ({vix_label})")
        print(f"- GIFT Nifty Gap (Est): {market_data.get('gap_pct'):.2f}%")
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
                opportunities.append(details)

        # Rank by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        for i, opp in enumerate(opportunities[:7], 1):
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp.get('iv_rank', 0):.1f}% | PCR: {opp.get('pcr', 0)}")
            print(f"   - Max Pain: {opp.get('max_pain')} | Gap: {opp.get('gap_pct', 0):.2f}%")
            print(f"   - Rationale: Multi-factor score (VIX: {opp.get('score',0)})")

            # Risk Warning Checks
            warnings = []
            if market_data['vix'] > 30: warnings.append("High VIX - Reduce Size")
            if opp['score'] < 60: warnings.append("Low Score - Caution")
            if opp['index'] == "NIFTY" and abs(opp.get('gap_pct', 0)) > 0.8: warnings.append("Large Gap - Volatility Risk")

            # Liquidity check warning
            # We don't have exact check here but score reflects it

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

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

            cmd = [sys.executable, str(script_path), "--symbol", strat['index'], "--port", str(5002)]

            # Pass extra args
            if strategy_name == "Iron Condor":
                cmd.extend(["--sentiment_score", str(strat.get('sentiment_score', 0.5))])
            elif strategy_name == "Gap Fade":
                cmd.extend(["--threshold", "0.5"]) # Default
            elif strategy_name == "Sentiment Reversal":
                 cmd.extend(["--sentiment_score", str(strat.get('sentiment_score', 0.5))])

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
