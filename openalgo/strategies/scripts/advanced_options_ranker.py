#!/usr/bin/env python3
import sys
import os
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import subprocess
import time

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient
from openalgo.strategies.utils.option_analytics import calculate_pcr, calculate_max_pain

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

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'record']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'war']

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

            # Normalize to 0.0 - 1.0 (0.5 is neutral)
            # Raw score ranges from -count to +count
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

        # 2. Spot Prices & Gap
        try:
            nifty_quote = self.client.get_quote("NIFTY 50", "NSE")
            data['nifty_spot'] = float(nifty_quote['ltp']) if nifty_quote else 0.0

            # Simple gap calculation using Open vs Prev Close (if available) or assume 0 if running live intra-day
            # Ideally we check yesterday's close.
            # Using simple heuristic: if 'open' is available in quote and we are near start
            if nifty_quote and 'open' in nifty_quote and 'close' in nifty_quote:
                 op = float(nifty_quote.get('open', 0))
                 cl = float(nifty_quote.get('close', 0)) # This might be prev close or current close
                 if op > 0 and cl > 0:
                     # If during day, gap is (Open - PrevClose) / PrevClose
                     # But 'close' field usually updates to LTP during day on some feeds.
                     # Let's assume 'close' is prev_close for now or 0.
                     data['gap_pct'] = ((op - cl) / cl) * 100 if cl > 0 else 0.0
            else:
                 data['gap_pct'] = 0.0
        except:
            data['nifty_spot'] = 0.0
            data['gap_pct'] = 0.0

        # 3. Sentiment
        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        # 4. Option Chains
        data['chains'] = {}
        for index in self.indices:
            try:
                # Map to Symbol expected by broker
                symbol = index
                if index == "NIFTY": symbol = "NIFTY"
                elif index == "BANKNIFTY": symbol = "BANKNIFTY"

                chain = self.client.get_option_chain(symbol)
                if chain:
                    data['chains'][index] = chain
            except Exception as e:
                logger.error(f"Failed to fetch chain for {index}: {e}")

        return data

    def calculate_iv_rank(self, index, vix):
        # Simplified: Use VIX as proxy for Index IV
        # IV Rank = (Current - Low) / (High - Low)
        # Assuming 1 year range 10 - 30 roughly
        low = 10
        high = 30
        return max(0, min(100, (vix - low) / (high - low) * 100))

    def analyze_strategy(self, strategy_type, index, market_data, chain_data):
        vix = market_data.get('vix', 15)
        pcr = calculate_pcr(chain_data)
        max_pain = calculate_max_pain(chain_data)
        sentiment = market_data.get('sentiment_score', 0.5)
        gap = market_data.get('gap_pct', 0)

        iv_rank = self.calculate_iv_rank(index, vix)

        scores = {}

        # --- 1. IV Rank Score ---
        # Selling: Wants High IV
        # Buying: Wants Low IV
        selling_strategies = ["Iron Condor", "Credit Spread", "Straddle"]
        buying_strategies = ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]

        if strategy_type in selling_strategies:
            scores['iv_rank'] = iv_rank
        else:
            scores['iv_rank'] = 100 - iv_rank

        # --- 2. Greeks Alignment ---
        # Conceptual scoring based on VIX context
        greeks_score = 50
        if strategy_type in selling_strategies:
             # Sell High Vega when VIX is high
             if vix > 18: greeks_score = 90
             elif vix < 12: greeks_score = 20
        elif strategy_type in buying_strategies:
             # Buy Low Vega when VIX is low
             if vix < 14: greeks_score = 90
             elif vix > 22: greeks_score = 30
        scores['greeks'] = greeks_score

        # --- 3. Liquidity Score ---
        # Assume major indices are liquid
        scores['liquidity'] = 90 if index == "NIFTY" else 80

        # --- 4. PCR/OI Pattern ---
        # Neutral strategies want PCR ~ 1.0
        # Directional want trend
        pcr_score = 50
        if strategy_type == "Iron Condor":
            dist = abs(pcr - 1.0)
            pcr_score = max(0, 100 - dist * 200)
        elif strategy_type == "Sentiment Reversal":
             # If PCR is extreme, reversal is likely
             if pcr > 1.4 or pcr < 0.6: pcr_score = 90
             else: pcr_score = 40
        scores['pcr_oi'] = pcr_score

        # --- 5. VIX Regime Score ---
        vix_score = 50
        if strategy_type in selling_strategies:
             if vix > 20: vix_score = 100 # Ideal for selling
             elif vix < 15: vix_score = 10
        else:
             if vix < 15: vix_score = 100 # Ideal for buying
             elif vix > 20: vix_score = 40
        scores['vix_regime'] = vix_score

        # --- 6. GIFT Nifty / Gap Bias ---
        gift_score = 50
        if strategy_type == "Gap Fade":
            if abs(gap) > 0.5: gift_score = 100
            else: gift_score = 10
        elif strategy_type == "Iron Condor":
            if abs(gap) < 0.3: gift_score = 100
            else: gift_score = 20
        scores['gift_nifty'] = gift_score

        # --- 7. Sentiment Score ---
        sent_score = 50
        if strategy_type == "Sentiment Reversal":
            # Needs extreme sentiment
            dist = abs(sentiment - 0.5)
            if dist > 0.3: sent_score = 100
            else: sent_score = 10
        elif strategy_type == "Iron Condor":
            # Needs neutral sentiment
            dist = abs(sentiment - 0.5)
            if dist < 0.15: sent_score = 100
            else: sent_score = 30
        scores['sentiment'] = sent_score

        # Composite
        final_score = 0
        for k, w in self.weights.items():
            final_score += scores.get(k, 0) * w

        return {
            'score': round(final_score, 1),
            'iv_rank': round(iv_rank, 1),
            'pcr': pcr,
            'max_pain': max_pain,
            'gap_pct': gap,
            'sentiment_score': sentiment,
            'details': scores
        }

    def generate_report(self):
        market_data = self.fetch_market_data()

        print(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d')}\n")

        vix = market_data.get('vix')
        vix_label = "High" if vix > 20 else ("Low" if vix < 15 else "Medium")
        print("📈 MARKET DATA SUMMARY:")
        print(f"- NIFTY Spot: {market_data.get('nifty_spot')} | VIX: {vix} ({vix_label})")
        print(f"- Gap (Est): {market_data.get('gap_pct'):.2f}%")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} (Score: {market_data.get('sentiment_score'):.2f})")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        opportunities = []

        for index in self.indices:
            chain = market_data['chains'].get(index)
            if not chain: continue

            for strategy in self.strategies:
                res = self.analyze_strategy(strategy, index, market_data, chain)
                res['strategy'] = strategy
                res['index'] = index
                opportunities.append(res)

        opportunities.sort(key=lambda x: x['score'], reverse=True)

        for i, opp in enumerate(opportunities[:7], 1):
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp['iv_rank']}% | PCR: {opp['pcr']} | Max Pain: {opp.get('max_pain')}")
            print(f"   - Rationale: Multi-factor alignment (VIX Regime: {opp['details']['vix_regime']}, Sentiment: {opp['details']['sentiment']})")

            # Risk Warnings
            warnings = []
            if market_data['vix'] > 30: warnings.append("High VIX")
            if opp['score'] < 60: warnings.append("Low Score")
            if abs(opp['gap_pct']) > 1.0 and opp['strategy'] == "Iron Condor": warnings.append("High Gap")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- [All]: Added Composite Scoring (IV, Greeks, Liquidity, PCR, VIX, Gap, Sentiment)")
        print("- [Iron Condor]: VIX & Sentiment Filters, Gap Protection")
        print("- [Gap Fade]: Gap Threshold Filters")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- Sentiment Reversal: Contrarian trade on extreme sentiment (>0.8 or <0.2)")

        to_deploy = [o for o in opportunities if o['score'] >= 70][:5]
        print("\n🚀 DEPLOYMENT PLAN:")
        if to_deploy:
            print(f"- Deploy: {', '.join([f'{x['strategy']} ({x['index']})' for x in to_deploy])}")
        else:
            print("- Deploy: None (No strategy > 70)")

        return to_deploy

    def deploy_strategies(self, strategies):
        for strat in strategies:
            name = strat['strategy']
            script = self.script_map.get(name)

            if not script:
                continue

            path = project_root / "openalgo" / "strategies" / "scripts" / script

            cmd = [sys.executable, str(path),
                   "--symbol", strat['index'],
                   "--port", str(5002)] # Port fixed to 5002 as requested

            # Additional args
            if name == "Iron Condor":
                cmd.extend(["--sentiment_score", str(strat['sentiment_score']), "--gap_pct", str(strat['gap_pct'])])
            elif name == "Sentiment Reversal":
                cmd.extend(["--sentiment_score", str(strat['sentiment_score'])])
            elif name == "Gap Fade":
                cmd.extend(["--threshold", "0.5"]) # Default

            logger.info(f"Deploying {name}: {' '.join(cmd)}")
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"Failed to deploy {name}: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", action="store_true", help="Deploy top strategies")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    ranker = AdvancedOptionsRanker(host=f"http://127.0.0.1:{args.port}")
    top = ranker.generate_report()

    if args.deploy and top:
        ranker.deploy_strategies(top)

if __name__ == "__main__":
    main()
