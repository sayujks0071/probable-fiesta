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
import yfinance as yf

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
            "Sentiment Reversal": "sentiment_reversal_strategy.py"
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
        """
        Estimate Gap using NIFTY previous close vs current spot or proxy.
        Since we might be running pre-market, we use yfinance for history.
        """
        try:
            logger.info("Fetching NIFTY history for Gap analysis...")
            # Fetch NIFTY 50 history
            ticker = yf.Ticker("^NSEI")
            hist = ticker.history(period="5d")

            if hist.empty:
                return 0.0, "Neutral"

            prev_close = hist['Close'].iloc[-1]
            if nifty_spot > 0:
                current_price = nifty_spot
            else:
                # If spot is 0 (pre-market), maybe use last close? No, need a proxy.
                # Assuming if spot is 0, we can't really calculate gap unless we have a pre-market feed.
                # Use current price from history if spot is not available (fallback)
                current_price = prev_close

            gap_pct = ((current_price - prev_close) / prev_close) * 100

            bias = "Neutral"
            if gap_pct > 0.2: bias = "Up"
            elif gap_pct < -0.2: bias = "Down"

            return gap_pct, bias

        except Exception as e:
            logger.warning(f"Error fetching GIFT Nifty proxy: {e}")
            return 0.0, "Neutral"

    def _fetch_news_sentiment(self):
        try:
            logger.info("Fetching News Sentiment...")
            url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
            try:
                response = requests.get(url, timeout=5)
            except:
                return 0.5, "Neutral", []

            if response.status_code != 200:
                return 0.5, "Neutral", []

            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'soar', 'record']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'recession', 'weak']

            score = 0
            count = 0
            key_events = []

            for item in items[:15]:
                title = item.title.text.lower()
                p_count = sum(1 for w in positive_words if w in title)
                n_count = sum(1 for w in negative_words if w in title)

                if p_count > n_count:
                    score += 1
                elif n_count > p_count:
                    score -= 1

                if count < 3:
                    key_events.append(item.title.text)

                count += 1

            if count == 0: return 0.5, "Neutral", []

            # Normalize score to 0.0 - 1.0 range
            # Range of score is -count to +count
            # (score + count) / (2 * count)

            normalized_score = (score + count) / (2 * count) if count > 0 else 0.5
            normalized_score = max(0.0, min(1.0, normalized_score))

            label = "Neutral"
            if normalized_score >= 0.6: label = "Positive"
            elif normalized_score <= 0.4: label = "Negative"

            return normalized_score, label, key_events

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return 0.5, "Neutral", []

    def fetch_market_data(self):
        logger.info("Fetching market data...")
        data = {}
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        data['vix'] = float(vix_quote['ltp']) if vix_quote else 15.0

        nifty_quote = self.client.get_quote("NIFTY 50", "NSE")
        data['nifty_spot'] = float(nifty_quote['ltp']) if nifty_quote else 0.0

        gap_pct, bias = self._fetch_gift_nifty_proxy(data['nifty_spot'])
        data['gap_pct'] = gap_pct
        data['gift_bias'] = bias

        score, label, events = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label
        data['key_events'] = events

        data['chains'] = {}
        for index in self.indices:
            exchange = "NFO" if index != "SENSEX" else "BFO"
            chain = self.client.get_option_chain(index, exchange)
            if chain:
                data['chains'][index] = chain

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
        spot = market_data.get('nifty_spot', 0) if index == "NIFTY" else 0
        if spot == 0 and chain_data:
             # Try to find spot from chain if possible or just skip strict checks
             pass

        pcr = calculate_pcr(chain_data)
        sentiment = market_data.get('sentiment_score', 0.5)
        gap = market_data.get('gap_pct', 0)

        # Determine average IV from ATM options for IV Rank
        # Placeholder: using VIX as proxy for Index IV
        iv_rank = self.calculate_iv_rank(index, vix)

        scores = {}
        details = {}

        # 1. IV Rank Score
        # Selling strategies favor High IV, Buying favor Low IV
        if strategy_type in ["Iron Condor", "Credit Spread", "Straddle"]:
            scores['iv_rank'] = iv_rank
        elif strategy_type in ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]:
            scores['iv_rank'] = 100 - iv_rank
        else:
            scores['iv_rank'] = 50

        # 2. VIX Regime Score
        # High VIX -> Sell, Low VIX -> Buy
        vix_score = 50
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             if vix > 20: vix_score = 100
             elif vix < 12: vix_score = 20
             else: vix_score = 60
        elif strategy_type in ["Calendar Spread"]:
             # Calendar spreads benefit from rising IV (buy back month), so low VIX is good entry
             if vix < 13: vix_score = 90
             elif vix > 20: vix_score = 10
        elif strategy_type in ["Debit Spread"]:
             if vix < 15: vix_score = 80
             elif vix > 25: vix_score = 20
        scores['vix_regime'] = vix_score

        # 3. Liquidity Score
        # Assume major indices are liquid
        scores['liquidity'] = 90

        # 4. PCR / OI Pattern Score
        pcr_score = 50
        # Reversal Logic
        if strategy_type == "Sentiment Reversal":
            if pcr > 1.3 or pcr < 0.6: pcr_score = 90
            else: pcr_score = 30
        elif strategy_type == "Iron Condor":
             # Neutral PCR preferred
             dist = abs(pcr - 1.0)
             if dist < 0.2: pcr_score = 90
             else: pcr_score = max(0, 100 - dist * 100)

        scores['pcr_oi'] = pcr_score
        details['pcr'] = pcr

        # 5. Greeks Alignment Score
        greeks_score = 50
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             # High Theta, Short Vega
             if vix > 18: greeks_score = 80
             else: greeks_score = 50
        scores['greeks'] = greeks_score

        # 6. GIFT Nifty Bias Score
        gift_score = 50
        if strategy_type == "Gap Fade":
             # Need significant gap
             if abs(gap) > 0.4: gift_score = 100
             elif abs(gap) > 0.2: gift_score = 60
             else: gift_score = 10
        elif strategy_type == "Iron Condor":
             # Need small gap
             if abs(gap) < 0.2: gift_score = 100
             else: gift_score = max(0, 100 - abs(gap)*200)

        scores['gift_nifty'] = gift_score

        # 7. News Sentiment Score
        sent_score = 50
        if strategy_type == "Sentiment Reversal":
             # Extreme sentiment
             dist = abs(sentiment - 0.5)
             if dist > 0.3: sent_score = 95
             else: sent_score = 20
        elif strategy_type == "Iron Condor":
             # Neutral sentiment
             dist = abs(sentiment - 0.5)
             if dist < 0.1: sent_score = 100
             else: sent_score = max(0, 100 - dist * 200)

        scores['sentiment'] = sent_score

        # Calculate Final
        final_score = self.calculate_composite_score(scores)
        details['score'] = round(final_score, 1)
        details['iv_rank'] = round(iv_rank, 1)
        details['sentiment_val'] = sentiment
        details['gap_pct'] = gap

        return details

    def generate_report(self):
        """Main execution flow."""
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        market_data = self.fetch_market_data()

        print("📈 MARKET DATA SUMMARY:")
        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 12 else "Medium")
        print(f"- NIFTY Spot: {market_data.get('nifty_spot')} | VIX: {vix} ({vix_label})")
        print(f"- GIFT Nifty Bias: {market_data.get('gift_bias')} | Gap: {market_data.get('gap_pct'):.2f}%")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} | Key Events: {', '.join(market_data.get('key_events', [])[:3])}")

        # Calculate NIFTY PCR for summary
        nifty_pcr = 0
        if "NIFTY" in market_data['chains']:
            nifty_pcr = calculate_pcr(market_data['chains']['NIFTY'])
        print(f"- PCR (NIFTY): {nifty_pcr:.2f}")

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
            print(f"   - IV Rank: {opp.get('iv_rank'):.1f}% | PCR: {opp.get('pcr'):.2f}")
            print(f"   - Rationale: Multi-factor score (VIX, Greeks, Sentiment, Gap)")

            # Risk Warning Checks
            warnings = []
            if market_data['vix'] > 30: warnings.append("High VIX - Reduce Size")
            if opp['score'] < 60: warnings.append("Low Score - Caution")
            if opp['index'] == "NIFTY" and abs(opp.get('gap_pct', 0)) > 0.8: warnings.append("Large Gap - Volatility Risk")
            if market_data.get('sentiment_label') == "Negative" and opp['strategy'] not in ["Sentiment Reversal", "Gap Fade"]: warnings.append("Negative Sentiment - Avoid Longs")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- [All]: Added Composite Scoring (IV, Greeks, Liquidity, PCR, VIX, Gap, Sentiment)")
        print("- [Iron Condor]: VIX & Sentiment Filters")
        print("- [Gap Fade]: Gap Threshold Filters")
        print("- [Sentiment Reversal]: New logic added")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- Sentiment Reversal: Targets mean reversion on extreme sentiment (>0.8 or <0.2)")
        print("- Gap Fade Strategy: Targets reversal of overnight gaps")

        print("\n🚀 DEPLOYMENT PLAN:")
        to_deploy = [opp for opp in opportunities if opp['score'] >= 70][:5]
        if to_deploy:
             print(f"- Deploy: {', '.join([f'{x['strategy']} ({x['index']})' for x in to_deploy])}")
             return to_deploy
        else:
             print("- Deploy: None (No strategy met score threshold >= 70)")
             return []

    def deploy_strategies(self, top_strategies):
        """Deploy top strategies."""
        logger.info(f"Deploying {len(top_strategies)} top strategies...")

        for strat in top_strategies:
            strategy_name = strat['strategy']
            script = self.script_map.get(strategy_name)

            if not script:
                # logger.warning(f"No script mapped for strategy '{strategy_name}'. Skipping deployment.")
                continue

            script_path = project_root / "openalgo" / "strategies" / "scripts" / script
            if not script_path.exists():
                logger.warning(f"Script file {script_path} not found.")
                continue

            cmd = [sys.executable, str(script_path), "--symbol", strat['index'], "--port", str(self.host.split(":")[-1])]

            # Pass extra args
            if strategy_name in ["Iron Condor", "Sentiment Reversal"]:
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
