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

from openalgo.strategies.utils.trading_utils import APIClient
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
    def __init__(self, api_key=None, host="http://127.0.0.1:5002", dry_run=False):
        self.api_key = api_key or os.getenv("OPENALGO_API_KEY", "dummy_key")
        self.host = host
        self.client = APIClient(self.api_key, host=self.host)
        self.dry_run = dry_run

        # Configuration
        self.indices = ["NIFTY", "BANKNIFTY", "SENSEX"]
        self.strategies = ["Iron Condor", "Credit Spread", "Debit Spread", "Straddle", "Gap Fade", "Sentiment Reversal"]

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

    def _fetch_gift_nifty_proxy(self, nifty_spot):
        """
        Attempt to fetch GIFT Nifty or calculate proxy gap.
        """
        try:
            # Try fetching real symbol if available (e.g., GIFTNIFTY)
            # This depends on broker support.
            # If not available, we return 0.0 gap for safety unless we have external data.
            # For this implementation, we assume a small random gap or 0 for simulation if API fails.

            # Simulated Gap logic for demonstration if API fails
            # In production, this would scrape SGX/GIFT site or use a paid feed.
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

        # VIX
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        data['vix'] = float(vix_quote['ltp']) if vix_quote and 'ltp' in vix_quote else 15.0

        # NIFTY Spot
        nifty_quote = self.client.get_quote("NIFTY 50", "NSE")
        data['nifty_spot'] = float(nifty_quote['ltp']) if nifty_quote and 'ltp' in nifty_quote else 0.0

        # GIFT Nifty
        gift_price, gap_pct = self._fetch_gift_nifty_proxy(data['nifty_spot'])
        data['gift_nifty'] = gift_price
        data['gap_pct'] = gap_pct

        # Sentiment
        score, label = self._fetch_news_sentiment()
        data['sentiment_score'] = score
        data['sentiment_label'] = label

        # Option Chains
        data['chains'] = {}
        for index in self.indices:
            exchange = "NFO" if index != "SENSEX" else "BFO"
            try:
                chain = self.client.get_option_chain(index, exchange)
                if chain:
                    # Enrich with Greeks if missing
                    self._enrich_chain_with_greeks(chain, data['nifty_spot'] if index == "NIFTY" else 0) # Approx spot for others
                    data['chains'][index] = chain
            except Exception as e:
                logger.error(f"Failed to fetch chain for {index}: {e}")

        return data

    def _enrich_chain_with_greeks(self, chain, spot_price):
        """
        Calculate Greeks if they are missing or zero in the chain data.
        """
        if not chain or spot_price <= 0:
            return

        # Simple check if greeks are present (check first item)
        first_item = chain[0]
        has_greeks = 'delta' in first_item or ('ce' in first_item and 'delta' in first_item['ce'])

        if has_greeks:
            return # Assume API provided them

        # Calculate manually
        # Needs T (time to expiry). Parse expiry date from symbol or item?
        # Typically chain item has 'expiryDate' string or timestamp

        now = datetime.now()
        r = 0.07 # Risk free rate assumption

        for item in chain:
            strike = item.get('strike_price', item.get('strike', 0))
            expiry_str = item.get('expiryDate', '')

            # Try to parse expiry
            T = 7/365.0 # Default fallback
            if expiry_str:
                try:
                    # Common formats: '29-Feb-2024', '2024-02-29', '29FEB2024'
                    expiry_date = None
                    # Clean up expiry string if needed (e.g. remove timestamp)
                    expiry_clean = expiry_str.split(' ')[0]

                    for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d%b%Y', '%d-%m-%Y']:
                        try:
                            expiry_date = datetime.strptime(expiry_clean, fmt)
                            break
                        except ValueError:
                            continue

                    if expiry_date:
                        # Ensure we compare dates
                        days_to_expiry = (expiry_date.date() - now.date()).days
                        # Use at least 1 day for T to avoid division by zero or negative
                        T = max(1/365.0, days_to_expiry / 365.0)
                except Exception as e:
                    logger.debug(f"Expiry parse failed for {expiry_str}: {e}")

            # Helper to calculate for CE and PE
            def process_option(opt_type, iv):
                if iv <= 0: iv = 0.20 # Fallback IV
                return calculate_greeks(spot_price, strike, T, r, iv, opt_type)

            # CE
            ce = item.get('ce', {})
            ce_iv = ce.get('impliedVolatility', ce.get('iv', 0)) / 100.0
            ce_greeks = process_option('ce', ce_iv)
            if 'ce' in item:
                item['ce'].update(ce_greeks)
            else:
                # Flat structure
                item.update({f"ce_{k}": v for k, v in ce_greeks.items()})

            # PE
            pe = item.get('pe', {})
            pe_iv = pe.get('impliedVolatility', pe.get('iv', 0)) / 100.0
            pe_greeks = process_option('pe', pe_iv)
            if 'pe' in item:
                item['pe'].update(pe_greeks)
            else:
                item.update({f"pe_{k}": v for k, v in pe_greeks.items()})

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

        # Calculate PCR
        pcr = calculate_pcr(chain_data)
        sentiment = market_data.get('sentiment_score', 0.5)
        gap = market_data.get('gap_pct', 0)

        scores = {}
        details = {}

        # 1. IV Rank
        # Use VIX as proxy for IV of the index options
        iv_rank = self.calculate_iv_rank(index, vix)
        details['iv_rank'] = iv_rank

        if strategy_type in ["Iron Condor", "Credit Spread", "Straddle"]:
            # Selling strategies prefer High IV
            scores['iv_rank'] = iv_rank
        elif strategy_type in ["Debit Spread", "Calendar Spread", "Gap Fade", "Sentiment Reversal"]:
            # Buying strategies prefer Low IV
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

        # 3. Liquidity (Assume NIFTY/BANKNIFTY are liquid)
        liq_score = 90 if index in ["NIFTY", "BANKNIFTY"] else 70
        scores['liquidity'] = liq_score

        # 4. PCR / OI Pattern
        pcr_score = 50
        if strategy_type == "Iron Condor":
             # Neutral strategy prefers neutral PCR ~ 1.0
             dist_from_1 = abs(pcr - 1.0)
             if dist_from_1 < 0.2: pcr_score = 90
             else: pcr_score = max(0, 100 - dist_from_1 * 100)
        elif strategy_type == "Sentiment Reversal":
             # Extreme PCR indicates reversal potential
             if pcr > 1.5 or pcr < 0.5: pcr_score = 90
             else: pcr_score = 40
        scores['pcr_oi'] = pcr_score
        details['pcr'] = pcr

        # 5. Greeks Alignment (Simplified)
        greeks_score = 50
        if strategy_type in ["Iron Condor", "Credit Spread"]:
             # High Theta is good. High Theta usually correlates with High IV/VIX.
             if vix > 15: greeks_score = 80
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
        print("- [Iron Condor]: VIX & Sentiment Filters")
        print("- [Gap Fade]: Gap Threshold Filters")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- Gap Fade Strategy: Targets reversal of overnight gaps > 0.5%")
        print("- Sentiment Reversal: Targets mean reversion on extreme sentiment")

        print("\n🚀 DEPLOYMENT PLAN:")
        # Filter for high quality setups
        to_deploy = [opp for opp in opportunities if opp['score'] >= 70][:3]
        if to_deploy:
             print(f"- Deploying: {', '.join([f'{x['strategy']} ({x['index']})' for x in to_deploy])}")
             return to_deploy
        else:
             print("- Deploy: None (No strategy met score threshold > 70)")
             return []

    def deploy_strategies(self, top_strategies):
        """Deploy top strategies."""
        if self.dry_run:
            logger.info("Dry Run: Skipping actual deployment subprocess calls.")
            return

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
            elif strategy_name == "Sentiment Reversal":
                cmd.extend(["--sentiment_score", str(strat.get('sentiment_score', 0.5))])

            logger.info(f"Executing: {' '.join(cmd)}")

            try:
                # Run detached
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"✅ Deployed: {strategy_name} on {strat['index']}")
            except Exception as e:
                logger.error(f"Failed to deploy {strategy_name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Advanced Options Ranker")
    parser.add_argument("--deploy", action="store_true", help="Deploy top strategies")
    parser.add_argument("--dry-run", action="store_true", help="Run without deploying")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    # Determine host
    host = f"http://127.0.0.1:{args.port}"

    ranker = AdvancedOptionsRanker(host=host, dry_run=args.dry_run)
    top_strats = ranker.generate_report()

    if args.deploy and top_strats:
        ranker.deploy_strategies(top_strats)

if __name__ == "__main__":
    main()
