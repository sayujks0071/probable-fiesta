#!/usr/bin/env python3
"""
AI Hybrid Reversion Breakout Strategy
Enhanced with EquityAnalyzer for Sector Rotation, Market Breadth, Earnings Filter, and VIX Sizing.
"""
import os
import sys
import time
import argparse
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.equity_analysis import EquityAnalyzer
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
except ImportError:
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../utils'))
        from equity_analysis import EquityAnalyzer
        from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
    except ImportError:
        print("Warning: openalgo package not found or imports failed.")
        sys.exit(1)

class AIHybridStrategy:
    def __init__(self, symbol, api_key, port, rsi_lower=30, rsi_upper=60, stop_pct=1.0, sector='NIFTY 50', earnings_date=None, logfile=None, time_stop_bars=12):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)

        # Initialize EquityAnalyzer
        self.analyzer = EquityAnalyzer(client=self.client)

        # Setup Logger
        self.logger = logging.getLogger(f"AIHybrid_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        if logfile:
            fh = logging.FileHandler(logfile)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

        self.pm = PositionManager(symbol) if PositionManager else None

        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.stop_pct = stop_pct
        self.sector = sector
        self.earnings_date = earnings_date
        self.time_stop_bars = time_stop_bars

    def calculate_signal(self, df):
        """Calculate signal for a given dataframe (Backtesting support)."""
        if df.empty or len(df) < 20:
            return 'HOLD', 0.0, {}

        # Use analyzer logic where appropriate, but indicators here are local to dataframe
        adx = self.analyzer.calculate_adx(df)
        df['rsi'] = self.analyzer.calculate_rsi(df['close'])

        df['sma20'] = df['close'].rolling(20).mean()
        df['std'] = df['close'].rolling(20).std()
        df['upper'] = df['sma20'] + (2 * df['std'])
        df['lower'] = df['sma20'] - (2 * df['std'])

        # Regime Filter (SMA200)
        df['sma200'] = df['close'].rolling(200).mean()

        last = df.iloc[-1]

        # Volatility Sizing (Target Risk)
        atr = self.analyzer.calculate_atr(df)
        risk_amount = 1000.0 # 1% of 100k

        if atr > 0:
            qty = int(risk_amount / (2.0 * atr))
            qty = max(1, min(qty, 500))
        else:
            qty = 50

        # Check Regime
        is_bullish_regime = True
        if not pd.isna(last.get('sma200')) and last['close'] < last['sma200']:
            is_bullish_regime = False

        # Reversion Logic: RSI < lower and Price < Lower BB
        if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * 1.2:
                return 'BUY', 1.0, {'type': 'REVERSION', 'rsi': last['rsi'], 'close': last['close'], 'quantity': qty}

        # Breakout Logic
        elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * 2.0 and is_bullish_regime:
                 return 'BUY', 1.0, {'type': 'BREAKOUT', 'rsi': last['rsi'], 'close': last['close'], 'quantity': qty}

        return 'HOLD', 0.0, {}

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting AI Hybrid for {self.symbol} (Sector: {self.sector})")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            try:
                # 1. Market Context via Analyzer
                regime = self.analyzer.get_market_regime()
                # 2. Earnings Filter (Local check if date passed)
                # ... (reuse existing logic or simplified)
                if self.earnings_date:
                    try:
                         e_date = datetime.strptime(self.earnings_date, "%Y-%m-%d").date()
                         if abs((e_date - datetime.now().date()).days) <= 2:
                             self.logger.info("Earnings approaching. Skipping.")
                             time.sleep(3600)
                             continue
                    except: pass

                # 3. VIX Sizing
                size_multiplier = 1.0
                if regime == 'VOLATILE':
                    size_multiplier = 0.5
                    self.logger.info("Volatile Market. Reducing size.")

                # 4. Market Breadth Filter
                breadth = self.analyzer.get_market_breadth()
                if breadth < 0.4:
                     self.logger.info(f"Weak Market Breadth ({breadth:.2f}). Skipping long entries.")
                     time.sleep(300)
                     continue

                # 5. Sector Rotation Filter
                if self.analyzer.get_sector_strength(self.sector) < 0.5:
                    self.logger.info(f"Sector {self.sector} Weak. Skipping.")
                    time.sleep(300)
                    continue

                # Fetch Data
                df = self.analyzer.fetch_data(self.symbol, interval="5m")

                if df.empty or len(df) < 20:
                    time.sleep(60)
                    continue

                # Indicators
                df['rsi'] = self.analyzer.calculate_rsi(df['close'])
                df['sma20'] = df['close'].rolling(20).mean()
                df['std'] = df['close'].rolling(20).std()
                df['upper'] = df['sma20'] + (2 * df['std'])
                df['lower'] = df['sma20'] - (2 * df['std'])

                last = df.iloc[-1]
                current_price = last['close']

                # Manage Position
                if self.pm and self.pm.has_position():
                    # ... (Existing Exit Logic)
                    entry = self.pm.entry_price
                    if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)):
                         self.pm.update_position(abs(self.pm.position), current_price, 'SELL')
                    elif (self.pm.position > 0 and current_price > last['sma20']): # Target
                         self.pm.update_position(abs(self.pm.position), current_price, 'SELL')
                    time.sleep(60)
                    continue

                # Reversion Logic
                if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * 1.2:
                        qty = int(100 * size_multiplier)
                        self.logger.info("Oversold Reversion Signal. BUY.")
                        self.pm.update_position(qty, current_price, 'BUY')

                # Breakout Logic
                elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * 2.0:
                         qty = int(100 * size_multiplier)
                         self.logger.info("Breakout Signal. BUY.")
                         self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='AI Hybrid Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key (or set OPENALGO_APIKEY env var)')
    parser.add_argument('--rsi_lower', type=float, default=35.0, help='RSI Lower Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')
    parser.add_argument('--earnings_date', type=str, help='Earnings Date YYYY-MM-DD')
    parser.add_argument("--logfile", type=str, help="Log file path")

    args = parser.parse_args()
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required via --api_key or OPENALGO_APIKEY")
        sys.exit(1)

    strategy = AIHybridStrategy(
        args.symbol,
        api_key,
        args.port,
        rsi_lower=args.rsi_lower,
        sector=args.sector,
        earnings_date=args.earnings_date,
        logfile=args.logfile
    )
    strategy.run()

# Module level wrapper
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {'rsi_lower': 30.0, 'rsi_upper': 60.0, 'stop_pct': 1.0, 'sector': 'NIFTY 50'}
    if params: strat_params.update(params)

    strat = AIHybridStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        rsi_lower=float(strat_params.get('rsi_lower', 30.0)),
        rsi_upper=float(strat_params.get('rsi_upper', 60.0)),
        stop_pct=float(strat_params.get('stop_pct', 1.0)),
        sector=strat_params.get('sector', 'NIFTY 50')
    )
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    global TIME_STOP_BARS
    TIME_STOP_BARS = getattr(strat, 'time_stop_bars', 12)

    return strat.calculate_signal(df)

# Global default for engine check
TIME_STOP_BARS = 12

if __name__ == "__main__":
    run_strategy()
