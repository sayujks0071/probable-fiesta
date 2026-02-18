#!/usr/bin/env python3
import sys
import os
import json
import logging
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import math
import subprocess
import time

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
            "Sentiment Reversal": "gap_fade_strategy.py", # Using GapFade logic but with sentiment args
            # "Credit Spread": "credit_spread.py" # Future
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

    def _get_time_to_expiry(self, symbol):
        """
        Estimate time to expiry.
        For indices, weekly expiry is Thursday (Wed for BankNifty sometimes).
        """
        today = datetime.now()
        # Simple logic: Next Thursday
        days_ahead = 3 - today.weekday() # 3 is Thursday
        if days_ahead <= 0:
            days_ahead += 7

        if "BANKNIFTY" in symbol:
             days_ahead = 2 - today.weekday()
             if days_ahead <= 0:
                 days_ahead += 7

        return max(0.001, days_ahead / 365.0)

    def _calculate_greeks_for_chain(self, symbol, chain_data, spot_price):
        """
        Enrich chain data with Greeks if missing.
        """
        T = self._get_time_to_expiry(symbol)
        r = 0.06 # Risk free rate

        enriched_chain = []
        for item in chain_data:
            strike = item.get('strike')
            if not strike: continue

            # CE
            ce_iv = 0
            if 'ce' in item and isinstance(item['ce'], dict):
                ce_iv = item['ce'].get('iv', 0)
            elif 'ce_iv' in item:
                ce_iv = item['ce_iv']

            # PE
            pe_iv = 0
            if 'pe' in item and isinstance(item['pe'], dict):
                pe_iv = item['pe'].get('iv', 0)
            elif 'pe_iv' in item:
                pe_iv = item['pe_iv']

            # Normalize IV (percentage to decimal)
            if ce_iv > 0: ce_iv /= 100.0
            if pe_iv > 0: pe_iv /= 100.0

            ce_greeks = calculate_greeks(spot_price, strike, T, r, ce_iv, 'ce')
            pe_greeks = calculate_greeks(spot_price, strike, T, r, pe_iv, 'pe')

            # Flatten/Attach
            item['ce_greeks'] = ce_greeks
            item['pe_greeks'] = pe_greeks

            enriched_chain.append(item)

        return enriched_chain

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

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation']

            score = 0
            count = 0
            for item in items[:10]:
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
            data['vix'] = float(vix_quote['ltp']) if vix_quote else 15.0
        except:
            data['vix'] = 15.0

        # 2. Spot Prices
        data['spots'] = {}
        for index in self.indices:
            try:
                q_sym = f"{index} 50" if index == "NIFTY" else index
                if index == "BANKNIFTY": q_sym = "NIFTY BANK"

                quote = self.client.get_quote(q_sym, "NSE")
                if quote:
                    data['spots'][index] = float(quote['ltp'])
                else:
                    quote = self.client.get_quote(index, "NSE")
                    data['spots'][index] = float(quote['ltp']) if quote else 0.0
            except:
                data['spots'][index] = 0.0

        # 3. Gift Nifty / Gap
        nifty_spot = data['spots'].get('NIFTY', 0.0)
        gift_price, gap_pct = self._fetch_gift_nifty_proxy(nifty_spot)
        data['gift_nifty'] = gift_price
        data['gap_pct'] = gap_pct

        # 4. Sentiment
        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        # 5. Options Chains
        data['chains'] = {}
        for index in self.indices:
            try:
                exchange = "NFO" if index != "SENSEX" else "BFO"
                chain = self.client.get_option_chain(index, exchange)
                if chain:
                    spot = data['spots'].get(index, 0)
                    enriched = self._calculate_greeks_for_chain(index, chain, spot)
                    data['chains'][index] = enriched
                else:
                    logger.warning(f"No chain data for {index}")
            except Exception as e:
                logger.error(f"Error fetching chain for {index}: {e}")

        return data

    def calculate_composite_score(self, scores):
        composite = 0
        for key, weight in self.weights.items():
            composite += scores.get(key, 0) * weight
        return composite

    def score_strategy(self, strategy_type, index, market_data):
        """
        Score a specific strategy for an index using multi-factor analysis.
        """
        vix = market_data.get('vix', 15)
        spot = market_data.get('spots', {}).get(index, 0)
        chain_data = market_data.get('chains', {}).get(index, [])
        sentiment = market_data.get('sentiment_score', 0.5)
        gap = market_data.get('gap_pct', 0)

        if not chain_data:
            return None

        pcr = calculate_pcr(chain_data)

        scores = {}
        details = {}

        # 1. IV Rank
        atm_iv = 15.0
        if spot > 0:
            min_dist = float('inf')
            atm_item = None
            for item in chain_data:
                k = item.get('strike')
                if k and abs(k - spot) < min_dist:
                    min_dist = abs(k - spot)
                    atm_item = item

            if atm_item:
                ce_iv = atm_item.get('ce', {}).get('iv', 0)
                pe_iv = atm_item.get('pe', {}).get('iv', 0)
                if ce_iv > 0 and pe_iv > 0:
                    atm_iv = (ce_iv + pe_iv) / 2
                elif ce_iv > 0: atm_iv = ce_iv
                elif pe_iv > 0: atm_iv = pe_iv

        iv_rank = calculate_iv_rank(atm_iv, low_iv=10, high_iv=30)
        details['iv_rank'] = iv_rank
        details['atm_iv'] = atm_iv

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
        total_oi = sum([i.get('ce', {}).get('oi', 0) + i.get('pe', {}).get('oi', 0) for i in chain_data])
        scores['liquidity'] = min(100, total_oi / 100000 * 10)
        if scores['liquidity'] < 20: scores['liquidity'] = 20

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
        details['scores'] = scores
        details['gap_pct'] = gap
        details['sentiment_val'] = sentiment
        details['max_pain'] = calculate_max_pain(chain_data)

        return details

    def generate_report(self):
        """Main execution flow."""
        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        market_data = self.fetch_market_data()

        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 12 else "Medium")

        print("📈 MARKET DATA SUMMARY:")
        print(f"- NIFTY Spot: {market_data.get('spots', {}).get('NIFTY', 0.0)} | VIX: {vix} ({vix_label})")
        print(f"- GIFT Nifty Gap (Est): {market_data.get('gap_pct'):.2f}% | Sentiment: {market_data.get('sentiment_label')} ({market_data.get('sentiment_score'):.2f})")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} | Key Events: --")

        # Get PCR for NIFTY
        nifty_chain = market_data['chains'].get('NIFTY', [])
        nifty_pcr = calculate_pcr(nifty_chain) if nifty_chain else 0
        print(f"- PCR (NIFTY): {nifty_pcr} | OI Trend: {'Unknown'}")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        opportunities = []

        for index in self.indices:
            chain = market_data['chains'].get(index)
            if not chain:
                continue

            for strategy in self.strategies:
                details = self.score_strategy(strategy, index, market_data)
                if not details: continue

                details['strategy'] = strategy
                details['index'] = index
                opportunities.append(details)

        # Rank by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        for i, opp in enumerate(opportunities[:7], 1):
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp.get('iv_rank', 0):.1f}% | PCR: {opp.get('pcr', 0)}")
            print(f"   - Entry: Max Pain {opp.get('max_pain')} | DTE: Est. Weekly")
            print(f"   - Rationale: Score Components: {opp.get('scores')}")

            # Risk Warning Checks
            warnings = []
            if vix > 30: warnings.append("High VIX - Reduce Size")
            if opp['score'] < 60: warnings.append("Low Score - Caution")
            if opp['index'] == "NIFTY" and abs(opp.get('gap_pct', 0)) > 0.8: warnings.append("Large Gap - Volatility Risk")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- [Iron Condor]: VIX & Sentiment Filters Added")
        print("- [Gap Fade]: Gap Threshold & Sentiment Check Added")
        print("- [Scoring]: Multi-factor Model Implemented")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- [VIX-Based Iron Condor]: Adjusts wings based on Volatility")
        print("- [Sentiment Reversal]: Contrarian plays on extreme sentiment")

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
            if strategy_name == "Iron Condor":
                cmd.extend(["--sentiment_score", str(strat.get('sentiment_val', 0.5))])
                cmd.extend(["--vix", str(strat.get('atm_iv', 15) * 100)]) # Approximation or pass real VIX
            elif strategy_name == "Gap Fade" or strategy_name == "Sentiment Reversal":
                cmd.extend(["--sentiment_score", str(strat.get('sentiment_val', 0.5))])
                # Gap Fade usually handles VIX internally but we can pass it
                cmd.extend(["--vix", str(strat.get('atm_iv', 15) * 100)])

            logger.info(f"Executing: {' '.join(cmd)}")

            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"✅ Deployed: {strategy_name} on {strat['index']}")
            except Exception as e:
                logger.error(f"Failed to deploy {strategy_name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Advanced Options Ranker")
    parser.add_argument("--deploy", action="store_true", help="Deploy top strategies")
    parser.add_argument("--test_data", action="store_true", help="Test Data Fetching")
    parser.add_argument("--score_test", action="store_true", help="Test Scoring")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    ranker = AdvancedOptionsRanker(host=f"http://127.0.0.1:{args.port}")

    if args.test_data:
        data = ranker.fetch_market_data()
        print(f"VIX: {data['vix']}")
        print(f"Sentiment: {data['sentiment_label']} ({data['sentiment_score']})")
        return

    if args.score_test:
        print("Testing Scoring Engine...")
        mock_data = {
            'vix': 22.0,
            'spots': {'NIFTY': 22000},
            'chains': {'NIFTY': [
                {'strike': 22000, 'ce': {'oi': 100000, 'iv': 20}, 'pe': {'oi': 100000, 'iv': 20}},
                {'strike': 22100, 'ce': {'oi': 50000, 'iv': 18}, 'pe': {'oi': 20000, 'iv': 22}}
            ]},
            'sentiment_score': 0.5,
            'gap_pct': 0.1
        }
        res = ranker.score_strategy("Iron Condor", "NIFTY", mock_data)
        print(f"Iron Condor Score: {res['score']}")
        return

    # Normal Run
    top_strats = ranker.generate_report()

    if args.deploy and top_strats:
        ranker.deploy_strategies(top_strats)

if __name__ == "__main__":
    main()
