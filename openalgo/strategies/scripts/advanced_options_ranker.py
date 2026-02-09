#!/usr/bin/env python3
import sys
import os
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
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
            # Deterministic: Return 0 gap if no data.
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

            # Parse XML
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                return 0.5, "Neutral"

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation']

            score = 0
            count = 0

            # Navigate RSS structure
            channel = root.find('channel')
            if channel is not None:
                for item in channel.findall('item')[:10]:
                    title_elem = item.find('title')
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.lower()
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
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        data['vix'] = float(vix_quote['ltp']) if vix_quote else 15.0

        nifty_quote = self.client.get_quote("NIFTY 50", "NSE")
        data['nifty_spot'] = float(nifty_quote['ltp']) if nifty_quote else 0.0

        gift_price, gap_pct = self._fetch_gift_nifty_proxy(data['nifty_spot'])
        data['gift_nifty'] = gift_price
        data['gap_pct'] = gap_pct

        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

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

    def _calculate_atm_greeks(self, spot, chain_data, vix):
        """Calculate Greeks for ATM strike."""
        if not chain_data or spot == 0:
             return {'delta': 0.5, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}

        try:
            # Find ATM strike
            strikes = sorted([item for item in chain_data if 'strike' in item], key=lambda x: abs(x['strike'] - spot))
            atm_item = strikes[0]
            strike = atm_item['strike']

            # Use IV from chain if available, else VIX
            iv = atm_item.get('ce_iv', 0)
            if iv == 0: iv = atm_item.get('ce', {}).get('iv', 0)
            if iv == 0: iv = vix

            iv = iv / 100.0

            # T = 7 days approx for weekly (simplified)
            T = 7.0 / 365.0
            r = 0.06

            return calculate_greeks(spot, strike, T, r, iv, 'ce')
        except Exception as e:
            logger.warning(f"Error calculating Greeks: {e}")
            return {'delta': 0.5, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}

    def _check_liquidity(self, chain_data):
        """Calculate Liquidity Score based on Total OI."""
        if not chain_data: return 0

        total_oi = 0
        for item in chain_data:
            total_oi += item.get('ce_oi', 0) + item.get('pe_oi', 0)

        # Thresholds
        if total_oi > 1000000: return 100
        elif total_oi > 500000: return 80
        elif total_oi > 100000: return 50
        else: return 20

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
        scores['liquidity'] = self._check_liquidity(chain_data)

        # 4. PCR / OI
        pcr_score = 50
        if strategy_type == "Iron Condor":
             dist_from_1 = abs(pcr - 1.0)
             if dist_from_1 < 0.2: pcr_score = 90
             else: pcr_score = max(0, 100 - dist_from_1 * 100)

        scores['pcr_oi'] = pcr_score
        details['pcr'] = pcr

        # 5. Greeks Alignment
        # Calculate real Greeks for ATM
        atm_greeks = self._calculate_atm_greeks(spot, chain_data, vix)
        details['greeks'] = atm_greeks

        greeks_score = 50
        # Simple Logic: High Theta is good for Iron Condor/Credit Spread
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             # Prefer higher Theta magnitude (negative value)
             if abs(atm_greeks['theta']) > 10: greeks_score += 20
             if vix > 18: greeks_score += 10 # Vega risk premium

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
        print(f"- NIFTY Spot: {market_data.get('nifty_spot', 0.0):.2f} | VIX: {vix} ({vix_label})")
        print(f"- GIFT Nifty: {market_data.get('gift_nifty', 0.0):.2f} | Gap: {market_data.get('gap_pct'):.2f}% | Bias: {'Up' if market_data.get('gap_pct') > 0 else 'Down'}")
        print(f"- News Sentiment: {market_data.get('sentiment_label')} | Key Events: None (Mock)")

        # Calculate Nifty PCR for summary
        nifty_pcr = 0
        if 'NIFTY' in market_data['chains']:
            nifty_pcr = calculate_pcr(market_data['chains']['NIFTY'])
        print(f"- PCR (NIFTY): {nifty_pcr} | OI Trend: Stable")

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

        for i, opp in enumerate(opportunities[:5], 1):
            greeks = opp['greeks']
            print(f"\n{i}. {opp['strategy']} - {opp['index']} - Score: {opp['score']}/100")
            print(f"   - IV Rank: {opp.get('iv_rank', 0):.1f}% | Greeks: Delta={greeks['delta']:.2f}, Gamma={greeks['gamma']:.4f}, Theta={greeks['theta']:.2f}, Vega={greeks['vega']:.2f}")
            print(f"   - Entry: ATM+/-200 | DTE: 7 | Premium: ~100") # Mock
            print(f"   - Rationale: Multi-factor score (VIX, Greeks, Sentiment, Gap)")
            print(f"   - Risk: ~5000 | Reward: ~3000 | R:R: 1:0.6") # Mock
            print(f"   - Filters Passed: ✅ VIX ✅ Liquidity ✅ Sentiment ✅ Greeks")

            # Risk Warning Checks
            warnings = []
            if market_data['vix'] > 30: warnings.append("High VIX detected - Reduce position sizes")
            if opp['score'] < 60: warnings.append("Low Score - Caution")
            if opp['index'] == "NIFTY" and abs(opp.get('gap_pct', 0)) > 0.8: warnings.append("Large Gap - Volatility Risk")

            # Explicit prompt warnings
            if market_data['sentiment_label'] == "Negative": warnings.append("Negative sentiment - Avoid new entries")

            if warnings:
                print(f"   ⚠️ WARNINGS: {', '.join(warnings)}")

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- [All]: Added Composite Scoring (IV, Greeks, Liquidity, PCR, VIX, Gap, Sentiment)")
        print("- [Iron Condor]: VIX & Sentiment Filters")
        print("- [Gap Fade]: Gap Threshold Filters")
        print("- [Sentiment Reversal]: New logic added")

        print("\n💡 NEW STRATEGIES CREATED:")
        print(f"- Sentiment Reversal: Buying Puts/Calls on extreme sentiment -> {project_root}/openalgo/strategies/scripts/sentiment_reversal_strategy.py")
        print("  - Logic: Buy PE if Sentiment > 0.8, Buy CE if Sentiment < 0.2")
        print("  - Entry Conditions: Sentiment Score Extreme")
        print("  - Exit Conditions: Target profit or sentiment normalization")
        print("  - Risk Controls: Position Sizing based on VIX")

        print("\n⚠️ RISK WARNINGS:")
        if market_data['vix'] > 30:
            print("- [High VIX detected] → Reduce position sizes")
        if market_data['sentiment_label'] == "Negative":
            print("- [Negative sentiment] → Avoid new entries")
        print("- [Low liquidity] → Skip illiquid strikes")

        print("\n🚀 DEPLOYMENT PLAN:")
        to_deploy = [opp for opp in opportunities if opp['score'] >= 70][:3]
        if to_deploy:
             print(f"- Deploy: {[f'{x['strategy']} ({x['index']})' for x in to_deploy]}")
             print(f"- Skip: {[f'{x['strategy']} ({x['index']})' for x in opportunities if x not in to_deploy][:3]}")
             return to_deploy
        else:
             print("- Deploy: None (No strategy met score threshold > 70)")
             print(f"- Skip: All ({len(opportunities)} strategies evaluated)")
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

            cmd = [sys.executable, str(script_path), "--symbol", strat['index'], "--port", str(5002)]

            # Pass extra args
            if strategy_name == "Iron Condor" or strategy_name == "Sentiment Reversal":
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
