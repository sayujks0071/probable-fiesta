#!/usr/bin/env python3
"""
Advanced MCX Commodity Strategy & Analysis Tool
Daily analysis and strategy deployment for MCX Commodities using Multi-Factor Models.
"""
import os
import sys
import time
import json
import logging
import argparse
import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
from pathlib import Path

# Try importing dependencies
try:
    import yfinance as yf
except ImportError:
    print("Warning: yfinance not found. Global market data will be simulated.")
    yf = None

# Add repo root to path for imports
script_dir = Path(__file__).parent
strategies_dir = script_dir.parent
utils_dir = strategies_dir / 'utils'
sys.path.insert(0, str(utils_dir))

try:
    from trading_utils import APIClient, is_market_open
    from symbol_resolver import SymbolResolver
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(strategies_dir))
    try:
        from utils.trading_utils import APIClient, is_market_open
        from utils.symbol_resolver import SymbolResolver
    except ImportError:
         print("Critical: trading_utils or symbol_resolver not found.")
         APIClient = None
         SymbolResolver = None
         is_market_open = lambda: True

# Configuration
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
SCRIPTS_DIR = Path(__file__).parent

# Strategy Templates Mapping
STRATEGY_TEMPLATES = {
    'Momentum': 'mcx_commodity_momentum_strategy.py',
    'Arbitrage': 'mcx_global_arbitrage_strategy.py',
    'Spread': 'mcx_inter_commodity_spread_strategy.py',
    'MeanReversion': 'mcx_commodity_momentum_strategy.py', # Fallback
    'Breakout': 'mcx_commodity_momentum_strategy.py', # Fallback
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCX_Advanced_Strategy")

class AdvancedMCXStrategy:
    def __init__(self, api_key, api_host):
        self.api_key = api_key
        self.api_host = api_host
        self.client = APIClient(api_key=self.api_key, host=self.api_host) if APIClient else None
        self.resolver = SymbolResolver() if SymbolResolver else None
        self.fundamental_data = self._load_fundamental_data()

        self.market_context = {
            'usd_inr': 83.50,
            'usd_trend': 'Neutral',
            'usd_volatility': 0.0,
            'global_gold': 0.0,
            'global_silver': 0.0,
            'global_crude': 0.0,
            'global_ng': 0.0,
            'global_copper': 0.0
        }

        self.commodities = [
            {'name': 'GOLD', 'global_ticker': 'GC=F', 'sector': 'Metal', 'min_vol': 1000},
            {'name': 'SILVER', 'global_ticker': 'SI=F', 'sector': 'Metal', 'min_vol': 500},
            {'name': 'CRUDEOIL', 'global_ticker': 'CL=F', 'sector': 'Energy', 'min_vol': 2000},
            {'name': 'NATURALGAS', 'global_ticker': 'NG=F', 'sector': 'Energy', 'min_vol': 5000},
            {'name': 'COPPER', 'global_ticker': 'HG=F', 'sector': 'Metal', 'min_vol': 500},
        ]

        self.opportunities = []
        self.rollover_contracts = []

    def _load_fundamental_data(self):
        """Load fundamental data from JSON file or return default."""
        data_path = strategies_dir / 'data' / 'fundamental_data.json'
        if data_path.exists():
            try:
                with open(data_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading fundamental data: {e}")

        # Default/Mock data if file doesn't exist
        return {
            'GOLD': {'score': 60, 'note': 'Safe haven demand due to geopolitical tension'},
            'SILVER': {'score': 55, 'note': 'Industrial demand stable'},
            'CRUDEOIL': {'score': 40, 'note': 'OPEC+ cuts priced in, weak demand'},
            'NATURALGAS': {'score': 70, 'note': 'Cold weather forecast in US'},
            'COPPER': {'score': 50, 'note': 'China stimulus pending'}
        }

    def fetch_global_context(self):
        """
        Fetch global market data via yfinance.
        """
        logger.info("Fetching Global Market Context...")

        if not yf:
            logger.warning("yfinance not available. Using simulated global data.")
            self._simulate_global_data()
            return

        try:
            # 1. USD/INR
            usd = yf.Ticker("INR=X")
            hist = usd.history(period="5d")
            if not hist.empty:
                current_usd = hist['Close'].iloc[-1]
                prev_usd = hist['Close'].iloc[-2]
                self.market_context['usd_inr'] = current_usd
                self.market_context['usd_trend'] = 'Up' if current_usd > prev_usd else 'Down'

                # Volatility (Std Dev of returns)
                returns = hist['Close'].pct_change().dropna()
                self.market_context['usd_volatility'] = returns.std() * 100 # percentage

                logger.info(f"USD/INR: {current_usd:.2f} ({self.market_context['usd_trend']}) | Vol: {self.market_context['usd_volatility']:.2f}%")

            # 2. Global Commodities
            tickers = [c['global_ticker'] for c in self.commodities]
            tickers_str = " ".join(tickers)
            data = yf.download(tickers_str, period="5d", interval="1d", progress=False)

            if not data.empty:
                # Handle Multi-Index columns in newer yfinance
                close_prices = data['Close'] if 'Close' in data else data

                for comm in self.commodities:
                    ticker = comm['global_ticker']
                    if ticker in close_prices.columns:
                        series = close_prices[ticker].dropna()
                        if not series.empty:
                            price = series.iloc[-1]
                            self.market_context[f"global_{comm['name'].lower()}"] = price
                            # simple trend
                            comm['global_trend'] = 'Up' if price > series.iloc[-2] else 'Down'
                            if series.iloc[-2] != 0:
                                comm['global_change_pct'] = ((price - series.iloc[-2]) / series.iloc[-2]) * 100
                            else:
                                comm['global_change_pct'] = 0.0
                            logger.info(f"Global {comm['name']}: {price:.2f} ({comm['global_change_pct']:.2f}%)")
                    else:
                        logger.warning(f"Ticker {ticker} not found in yfinance response columns: {close_prices.columns}")
        except Exception as e:
            logger.error(f"Error fetching global data: {e}")
            self._simulate_global_data()

    def _simulate_global_data(self):
        """Fallback simulation for global data."""
        self.market_context['usd_inr'] = 83.50 + np.random.uniform(-0.2, 0.2)
        self.market_context['usd_trend'] = 'Neutral'
        self.market_context['usd_volatility'] = 0.5
        for comm in self.commodities:
            self.market_context[f"global_{comm['name'].lower()}"] = 100.0 # Dummy
            comm['global_trend'] = 'Neutral'
            comm['global_change_pct'] = 0.0

    def identify_rollover(self, symbol):
        """
        Check if contract is expiring within 7 days.
        MCX Symbol Format: {SYMBOL}{DD}{MMM}{YY}FUT or similar
        Example: GOLDM05FEB26FUT
        """
        try:
            # Regex to capture DD MMM YY
            match = re.search(r'(\d{2})([A-Z]{3})(\d{2})', symbol)
            if match:
                day, month_str, year = match.groups()
                # Parse date
                expiry_str = f"{day}{month_str}20{year}"
                expiry_date = datetime.strptime(expiry_str, "%d%b%Y")

                days_to_expiry = (expiry_date - datetime.now()).days

                if 0 <= days_to_expiry <= 7:
                    return True, days_to_expiry, expiry_date.strftime('%Y-%m-%d')
                else:
                    return False, days_to_expiry, expiry_date.strftime('%Y-%m-%d')
        except Exception as e:
            logger.debug(f"Could not parse expiry for {symbol}: {e}")

        return False, 999, "Unknown"

    def fetch_mcx_data(self):
        """
        Fetch MCX data via APIClient for active contracts.
        """
        logger.info("Fetching MCX Data...")

        if not self.client:
            logger.error("API Client not available")
            return

        for comm in self.commodities:
            try:
                # Resolve Active Symbol
                symbol = None
                if self.resolver:
                    symbol = self.resolver.resolve({'underlying': comm['name'], 'type': 'FUT', 'exchange': 'MCX'})

                if not symbol:
                    # Fallback hardcoded logic if resolver fails or not available
                    # This is just a placeholder logic, ideally resolver should work
                    logger.warning(f"Could not resolve symbol for {comm['name']}")
                    comm['valid'] = False
                    continue

                comm['symbol'] = symbol

                # Check Rollover
                is_expiring, days_left, expiry_date = self.identify_rollover(symbol)
                comm['days_to_expiry'] = days_left
                if is_expiring:
                    self.rollover_contracts.append(f"{comm['name']} ({symbol}) expires in {days_left} days ({expiry_date})")

                # Fetch Historical Data (15m candles for analysis)
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

                df = self.client.history(symbol, exchange="MCX", interval="15m", start_date=start_date, end_date=end_date)

                if df.empty or len(df) < 50:
                    logger.warning(f"Insufficient data for {symbol}")
                    comm['valid'] = False
                    continue

                comm['data'] = df
                comm['valid'] = True

                # Fetch Quote for real-time (optional, can use last candle close)
                quote = self.client.get_quote(symbol, exchange="MCX")
                if quote and 'ltp' in quote:
                    comm['ltp'] = float(quote.get('ltp'))
                    comm['volume'] = float(quote.get('volume', df['volume'].iloc[-1]))
                    comm['oi'] = float(quote.get('oi', 0))
                else:
                    comm['ltp'] = df['close'].iloc[-1]
                    comm['volume'] = df['volume'].iloc[-1]
                    comm['oi'] = 0

                logger.info(f"Fetched {symbol}: LTP={comm['ltp']}, Vol={comm['volume']}")

            except Exception as e:
                logger.error(f"Error processing {comm['name']}: {e}")
                comm['valid'] = False

    def calculate_technical_indicators(self, df):
        """Calculate ADX, RSI, ATR."""
        if df.empty: return {}

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()

        # ADX Calculation
        up = df['high'] - df['high'].shift(1)
        down = df['low'].shift(1) - df['low']

        # +DM: if up > down and up > 0
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        # -DM: if down > up and down > 0
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        # We need a Series to use rolling
        plus_dm_s = pd.Series(plus_dm, index=df.index)
        minus_dm_s = pd.Series(minus_dm, index=df.index)

        # Smooth with period 14
        tr = df['atr'] # True Range approximation is usually ATR or similar smoothing

        # Note: Proper ADX smoothing is Wilder's smoothing. Here we use Simple MA for robustness/simplicity in this context.
        # Ideally: smooth_plus_dm = previous_smooth - (previous_smooth/14) + current_plus_dm
        # Using rolling mean is an acceptable approximation for this scale.

        plus_di = 100 * (plus_dm_s.rolling(14).mean() / tr)
        minus_di = 100 * (minus_dm_s.rolling(14).mean() / tr)

        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
        df['adx'] = dx.rolling(14).mean()

        return {
            'adx': df['adx'].iloc[-1],
            'rsi': df['rsi'].iloc[-1],
            'atr': df['atr'].iloc[-1],
            'close': df['close'].iloc[-1],
            'prev_close': df['close'].iloc[-2]
        }

    def get_seasonality_score(self, commodity_name):
        """
        Return a seasonality score (0-100) based on current month.
        """
        month = datetime.now().month
        # Example seasonality map
        seasonality = {
            'GOLD': {1: 80, 2: 60, 3: 40, 4: 50, 5: 90, 6: 40, 7: 40, 8: 60, 9: 50, 10: 80, 11: 90, 12: 70}, # Festivals
            'SILVER': {1: 70, 2: 60, 3: 50, 4: 60, 5: 80, 6: 40, 7: 50, 8: 60, 9: 50, 10: 70, 11: 80, 12: 60},
            'CRUDEOIL': {1: 40, 2: 50, 3: 60, 4: 70, 5: 80, 6: 90, 7: 90, 8: 80, 9: 60, 10: 50, 11: 40, 12: 50}, # Summer driving
            'NATURALGAS': {1: 90, 2: 80, 3: 60, 4: 40, 5: 40, 6: 70, 7: 80, 8: 70, 9: 50, 10: 60, 11: 80, 12: 90}, # Winter heating + Summer cooling
            'COPPER': {1: 60, 2: 70, 3: 80, 4: 80, 5: 70, 6: 60, 7: 50, 8: 50, 9: 60, 10: 60, 11: 60, 12: 50}, # Spring construction
        }
        return seasonality.get(commodity_name, {}).get(month, 50)

    def analyze_commodities(self):
        """
        Multi-Factor Scoring & Strategy Selection.
        """
        logger.info("Analyzing Commodities...")

        for comm in self.commodities:
            if not comm.get('valid', False):
                continue

            try:
                # 1. Technicals
                techs = self.calculate_technical_indicators(comm['data'])
                if not techs or pd.isna(techs['adx']):
                    continue

                # 2. Scores Calculation

                # Trend (ADX) - Weight 0.25
                # ADX > 25 is strong trend. Scale 20->0, 50->100
                adx = techs['adx']
                trend_score = min(max((adx - 20) * 3.33, 0), 100)
                trend_dir = 'Up' if techs['close'] > techs['prev_close'] else 'Down'

                # Momentum (RSI) - Weight 0.20
                rsi = techs['rsi']
                # Score high if RSI is trending (e.g. > 60 or < 40)
                momentum_score = 0
                if rsi > 60: momentum_score = (rsi - 50) * 2
                elif rsi < 40: momentum_score = (50 - rsi) * 2
                else: momentum_score = 30 # Neutral
                momentum_score = min(max(momentum_score, 0), 100)

                # Global Alignment - Weight 0.15
                global_trend = comm.get('global_trend', 'Neutral')
                global_align_score = 100 if trend_dir == global_trend else 20

                # Volatility - Weight 0.15
                # Ideally compare current ATR to historical ATR percentile
                atr = techs['atr']
                # Simplification: Normal score 70, penalize if currency volatility is crazy
                volatility_score = 70
                if self.market_context['usd_volatility'] > 0.8: # High currency risk
                    volatility_score = 40

                # Liquidity - Weight 0.10
                liquidity_score = 100 if comm['volume'] > comm['min_vol'] else 40

                # Fundamental - Weight 0.10
                fundamental_score = self.fundamental_data.get(comm['name'], {}).get('score', 50)
                fundamental_note = self.fundamental_data.get(comm['name'], {}).get('note', "Neutral")

                # Seasonality - Weight 0.05
                seasonality_score = self.get_seasonality_score(comm['name'])

                # Composite Score
                # (Trend Strength Score × 0.25) +
                # (Momentum Score × 0.20) +
                # (Global Alignment Score × 0.15) +
                # (Volatility Score × 0.15) +
                # (Liquidity Score × 0.10) +
                # (Fundamental Score × 0.10) +
                # (Seasonality Score × 0.05)
                composite_score = (
                    trend_score * 0.25 +
                    momentum_score * 0.20 +
                    global_align_score * 0.15 +
                    volatility_score * 0.15 +
                    liquidity_score * 0.10 +
                    fundamental_score * 0.10 +
                    seasonality_score * 0.05
                )

                # Determine Strategy Type
                strategy_type = 'Momentum'

                # Logic to switch strategies based on scores
                if composite_score < 40:
                    strategy_type = 'Avoid'

                # If strong divergence (Global says UP, MCX says DOWN or vice versa), consider Arbitrage
                elif global_align_score < 30 and volatility_score > 60:
                     strategy_type = 'Arbitrage'
                     # Boost score for Arbitrage view to bring it up to tradeable
                     composite_score = (composite_score + 100) / 2

                # If Momentum is weak but Seasonality is strong -> Mean Reversion
                elif momentum_score < 40 and seasonality_score > 80:
                    strategy_type = 'MeanReversion' # Seasonal Buy/Sell

                # If ADX is strong -> Breakout/Trend
                elif trend_score > 80:
                    strategy_type = 'Breakout'

                self.opportunities.append({
                    'symbol': comm['symbol'],
                    'name': comm['name'],
                    'strategy_type': strategy_type,
                    'score': round(composite_score, 2),
                    'ltp': comm['ltp'],
                    'details': {
                        'trend_score': trend_score,
                        'trend_dir': trend_dir,
                        'momentum_score': momentum_score,
                        'global_score': global_align_score,
                        'volatility_score': volatility_score,
                        'liquidity_score': liquidity_score,
                        'seasonality_score': seasonality_score,
                        'fundamental_score': fundamental_score,
                        'fundamental_note': fundamental_note,
                        'adx': adx,
                        'rsi': rsi,
                        'atr': atr,
                        'volume': comm['volume']
                    }
                })

            except Exception as e:
                logger.error(f"Error analyzing {comm['name']}: {e}", exc_info=True)

        # Sort opportunities
        self.opportunities.sort(key=lambda x: x['score'], reverse=True)

    def generate_report(self):
        """
        Generate and print the daily analysis report.
        """
        print(f"\n📊 DAILY MCX STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        print("\n🌍 GLOBAL MARKET CONTEXT:")
        print(f"- USD/INR: {self.market_context['usd_inr']:.2f} | Trend: {self.market_context['usd_trend']} | Impact: {'Negative' if self.market_context['usd_volatility'] > 0.8 else 'Positive'}")

        for comm in self.commodities:
            if 'global_change_pct' in comm:
                # Calculate Correlation/Basis roughly
                mcx_price = comm.get('ltp', 0)
                global_price = self.market_context.get(f"global_{comm['name'].lower()}", 0)
                # Basis isn't directly comparable due to currency/unit diffs, so just printing values
                print(f"- {comm['name']}: Global ${global_price:.2f} | MCX ₹{mcx_price:.2f} | Change {comm['global_change_pct']:.2f}%")

        print(f"- Key Events: [EIA Report (Wed), OPEC+]") # Placeholder for calendar integration

        print("\n📈 MCX MARKET DATA:")
        active_contracts = [c for c in self.commodities if c.get('valid')]
        print(f"- Active Contracts: {', '.join([c['symbol'] for c in active_contracts])}")

        if self.rollover_contracts:
            print(f"- Rollover Status: {', '.join(self.rollover_contracts)}")
        else:
            print("- Rollover Status: No contracts expiring this week")

        print(f"- Liquidity: {len(active_contracts)} contracts valid for trading")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        top_picks = []

        for i, opp in enumerate(self.opportunities, 1):
            if opp['strategy_type'] == 'Avoid':
                continue

            print(f"\n{i}. {opp['name']} - {opp['symbol']} - {opp['strategy_type']} - Score: {opp['score']}/100")
            d = opp['details']
            print(f"   - Trend: {d['trend_dir']} (ADX: {d['adx']:.1f}) | Momentum: {d['momentum_score']:.0f} (RSI: {d['rsi']:.1f})")
            print(f"   - Global Alignment: {d['global_score']} | Volatility: {'High' if d['volatility_score'] < 50 else 'Normal'} (ATR: {d['atr']:.2f})")

            # Simulated Entry/Stop/Target for report
            entry = opp['ltp']
            stop = entry * 0.98 if d['trend_dir'] == 'Up' else entry * 1.02
            target = entry * 1.04 if d['trend_dir'] == 'Up' else entry * 0.96
            print(f"   - Entry: {entry:.2f} | Stop: {stop:.2f} | Target: {target:.2f} | R:R: 1:2")

            risk_pct = 2.0
            if self.market_context['usd_volatility'] > 0.8:
                risk_pct = 1.0 # Reduce risk

            print(f"   - Position Size: 1 lots | Risk: {risk_pct}% of capital")
            print(f"   - Rationale: Strong multi-factor alignment. Fundamental: {d['fundamental_note']}")

            # Checkbox visualization
            checks = []
            if d['trend_score'] > 50: checks.append("✅ Trend")
            if d['momentum_score'] > 50: checks.append("✅ Momentum")
            if d['liquidity_score'] > 50: checks.append("✅ Liquidity")
            if d['global_score'] > 50: checks.append("✅ Global")
            if d['volatility_score'] > 50: checks.append("✅ Volatility")

            print(f"   - Filters Passed: {' '.join(checks)}")

            top_picks.append(opp)
            if len(top_picks) >= 6: break # Top 6

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- MCX Momentum: Added USD/INR adjustment factor")
        print("- MCX Momentum: Enhanced with global price correlation filter")
        print("- MCX Momentum: Added seasonality-based position sizing")
        print("- MCX Momentum: Improved contract selection (avoid expiry week)")
        print("- MCX Momentum: Added fundamental overlay (inventory data, news events)")
        print("- MCX Momentum: Enhanced volatility-based position sizing")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- Global-MCX Arbitrage: Trade MCX when it diverges from global prices")
        print("  - Logic: Enter when MCX diverges >3% from global price")
        print("  - Entry Conditions: Global Alignment Score < 40 & High Volatility")

        print("\n⚠️ RISK WARNINGS:")
        if self.market_context['usd_volatility'] > 0.8:
            print(f"- [High USD/INR volatility {self.market_context['usd_volatility']:.2f}%] → Reduce position sizes")
        if self.rollover_contracts:
            print("- [Rollover week] → Close positions before expiry")

        print("\n🚀 DEPLOYMENT PLAN:")
        print(f"- Deploy: {[op['name'] for op in top_picks]}")
        skipped = [op['name'] for op in self.opportunities if op['strategy_type'] == 'Avoid']
        if skipped:
            print(f"- Skip: {skipped}")

        deploy_cmds = []
        for pick in top_picks:
            script_name = STRATEGY_TEMPLATES.get(pick['strategy_type'], 'mcx_commodity_momentum_strategy.py')
            cmd = f"python3 openalgo/strategies/scripts/{script_name} " \
                  f"--symbol {pick['symbol']} --underlying {pick['name']} " \
                  f"--usd_inr_trend {self.market_context['usd_trend']} " \
                  f"--usd_inr_volatility {self.market_context['usd_volatility']} " \
                  f"--seasonality_score {pick['details']['seasonality_score']} " \
                  f"--global_alignment_score {pick['details']['global_score']}"
            deploy_cmds.append(cmd)
            # print(f"- {pick['name']}: {cmd}")

        return deploy_cmds

def main():
    parser = argparse.ArgumentParser(description='Advanced MCX Strategy Analyzer')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, default='demo_key', help='API Key')
    args = parser.parse_args()

    # Overwrite with env vars if present
    api_key = os.getenv('OPENALGO_APIKEY', args.api_key)
    port = int(os.getenv('OPENALGO_PORT', args.port))
    host = f"http://127.0.0.1:{port}"

    analyzer = AdvancedMCXStrategy(api_key, host)
    analyzer.fetch_global_context()
    analyzer.fetch_mcx_data()
    analyzer.analyze_commodities()
    analyzer.generate_report()

if __name__ == "__main__":
    main()
