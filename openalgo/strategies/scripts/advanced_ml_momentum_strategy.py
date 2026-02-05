#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay using EquityAnalyzer.
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
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
except ImportError:
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../utils'))
        from equity_analysis import EquityAnalyzer
        from trading_utils import APIClient, PositionManager, is_market_open
    except ImportError:
        print("Warning: openalgo package not found or imports failed.")
        sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class MLMomentumStrategy:
    def __init__(self, symbol, api_key, port, threshold=0.01, stop_pct=1.0, sector='NIFTY 50', vol_multiplier=0.5):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)
        self.logger = logging.getLogger(f"MLMomentum_{symbol}")
        self.pm = PositionManager(symbol) if PositionManager else None

        # Initialize EquityAnalyzer
        self.analyzer = EquityAnalyzer(client=self.client)

        self.roc_threshold = threshold
        self.stop_pct = stop_pct
        self.sector = sector
        self.vol_multiplier = vol_multiplier

    def check_time_filter(self):
        """Avoid trading during low volume lunch hours (12:00 - 13:00)."""
        now = datetime.now()
        if 12 <= now.hour < 13:
            return False
        return True

    def calculate_signal(self, df):
        """Calculate signal for backtesting."""
        if df.empty or len(df) < 50:
            return 'HOLD', 0.0, {}

        adx = self.analyzer.calculate_adx(df)
        df['rsi'] = self.analyzer.calculate_rsi(df['close'])
        df['roc'] = df['close'].pct_change(periods=10)
        df['sma50'] = df['close'].rolling(50).mean()

        last = df.iloc[-1]
        current_price = last['close']

        # Mock external factors for pure backtest
        rs_excess = 0.01
        sector_outperformance = 0.01
        sentiment = 0.5

        if (last['roc'] > self.roc_threshold and
            last['rsi'] > 55 and
            rs_excess > 0 and
            sector_outperformance > 0 and
            current_price > last['sma50'] and
            sentiment >= 0): # Sentiment used here

            # Volume check
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * self.vol_multiplier:
                return 'BUY', 1.0, {'roc': last['roc'], 'rsi': last['rsi']}

        return 'HOLD', 0.0, {}

    def run(self):
        self.logger.info(f"Starting ML Momentum Strategy for {self.symbol} (Sector: {self.sector})")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            # Time Filter
            if not self.check_time_filter():
                # If we have a position, we might hold, but no new entries
                if not (self.pm and self.pm.has_position()):
                    self.logger.info("Lunch hour (12:00-13:00). Skipping new entries.")
                    time.sleep(300)
                    continue

            try:
                # 1. Fetch Stock Data via Analyzer
                df = self.analyzer.fetch_data(self.symbol, interval="15m", period_days=5)
                if df.empty or len(df) < 50:
                    time.sleep(60)
                    continue

                # 2. Indicators
                df['roc'] = df['close'].pct_change(periods=10)
                df['rsi'] = self.analyzer.calculate_rsi(df['close'])
                df['sma50'] = df['close'].rolling(50).mean()

                last = df.iloc[-1]
                current_price = last['close']

                # 3. Enhanced Factors
                # Relative Strength vs NIFTY
                nifty_df = self.analyzer.fetch_data("NIFTY 50", interval="15m", period_days=5)
                rs_excess = 0.0
                if not nifty_df.empty:
                    stock_ret = df['close'].pct_change(10).iloc[-1]
                    nifty_ret = nifty_df['close'].pct_change(10).iloc[-1]
                    rs_excess = stock_ret - nifty_ret

                # Sector Momentum
                sector_strength = self.analyzer.get_sector_strength(self.sector)

                # News Sentiment (Mocked or implemented in analyzer later)
                sentiment = 0.5

                # Manage Position
                if self.pm and self.pm.has_position():
                    entry = self.pm.entry_price
                    if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)):
                        self.logger.info(f"Stop Loss Hit.")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL')
                    elif (self.pm.position > 0 and last['rsi'] < 50):
                         self.logger.info(f"Momentum Faded (RSI < 50). Exit.")
                         self.pm.update_position(abs(self.pm.position), current_price, 'SELL')
                    time.sleep(60)
                    continue

                # Entry Logic
                if (last['roc'] > self.roc_threshold and
                    last['rsi'] > 55 and
                    rs_excess > 0 and
                    sector_strength > 0.5 and
                    current_price > last['sma50'] and
                    sentiment >= 0): # Sentiment check added

                    # Volume check
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * self.vol_multiplier:
                        self.logger.info(f"Strong Momentum Signal. BUY.")
                        self.pm.update_position(100, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='ML Momentum Strategy')
    parser.add_argument('--symbol', type=str, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, default='demo_key', help='API Key')
    parser.add_argument('--threshold', type=float, default=0.01, help='ROC Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')

    args = parser.parse_args()
    
    symbol = args.symbol or os.getenv('SYMBOL')
    if not symbol:
        print("ERROR: --symbol argument or SYMBOL environment variable is required")
        sys.exit(1)
    
    port = args.port or int(os.getenv('OPENALGO_PORT', '5001'))
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
    threshold = args.threshold or float(os.getenv('THRESHOLD', '0.01'))

    strategy = MLMomentumStrategy(symbol, api_key, port, threshold=threshold, sector=args.sector)
    strategy.run()

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'threshold': 0.01,
        'stop_pct': 1.0,
        'sector': 'NIFTY 50',
        'vol_multiplier': 0.5
    }
    if params:
        strat_params.update(params)

    strat = MLMomentumStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        threshold=float(strat_params.get('threshold', 0.01)),
        stop_pct=float(strat_params.get('stop_pct', 1.0)),
        sector=strat_params.get('sector', 'NIFTY 50'),
        vol_multiplier=float(strat_params.get('vol_multiplier', 0.5))
    )
    # Silence logger
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())
    return strat.calculate_signal(df)

if __name__ == "__main__":
    run_strategy()
