#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
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
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')

# Add utils directory to path for imports
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open
    from risk_manager import RiskManager
except ImportError:
    try:
        # Try absolute import
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open
        from utils.risk_manager import RiskManager
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
            from openalgo.strategies.utils.risk_manager import RiskManager
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            RiskManager = None
            is_market_open = lambda: True

class MLMomentumStrategy:
    def __init__(self, symbol, api_key, port, threshold=0.01, stop_pct=1.0, sector='NIFTY 50', vol_multiplier=0.5):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)
        self.logger = logging.getLogger(f"MLMomentum_{symbol}")

        # Initialize Risk Manager
        self.rm = None
        if RiskManager:
            self.rm = RiskManager(
                strategy_name=f"MLMomentum_{symbol}",
                exchange="NSE",
                capital=100000,
                config={'max_loss_per_trade_pct': stop_pct}
            )

        self.roc_threshold = threshold
        self.stop_pct = stop_pct
        self.sector = sector
        self.vol_multiplier = vol_multiplier

    def calculate_signal(self, df):
        """Calculate signal for backtesting."""
        if df.empty or len(df) < 50:
            return 'HOLD', 0.0, {}

        # Indicators
        df['roc'] = df['close'].pct_change(periods=10)

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs_val = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs_val))

        # SMA for Trend
        df['sma50'] = df['close'].rolling(50).mean()

        last = df.iloc[-1]
        current_price = last['close']

        # Simplifications for Backtest (Missing Index/Sector Data)
        rs_excess = 0.0
        sector_outperformance = 0.0
        sentiment = 0.5 # Mock positive

        # Entry Logic
        # Require strict signal for real trading, but for backtest without index data, we might be lenient
        # if specifically testing just this module logic.
        # However, for production readiness, we remove forced positives.

        if (last['roc'] > self.roc_threshold and
            last['rsi'] > 55 and
            current_price > last['sma50']):

            # Volume check
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > avg_vol * self.vol_multiplier: # Stricter volume
                return 'BUY', 1.0, {'roc': last['roc'], 'rsi': last['rsi']}

        return 'HOLD', 0.0, {}

    def calculate_relative_strength(self, df, index_df):
        if index_df.empty: return 1.0

        # Align timestamps (simplistic approach using last N periods)
        try:
            stock_roc = df['close'].pct_change(10).iloc[-1]
            index_roc = index_df['close'].pct_change(10).iloc[-1]
            return stock_roc - index_roc # Excess Return
        except:
            return 0.0

    def get_news_sentiment(self):
        # Simulated
        return 0.5 # Neutral to Positive

    def check_time_filter(self):
        """Avoid trading during low volume lunch hours (12:00 - 13:00)."""
        now = datetime.now()
        if 12 <= now.hour < 13:
            return False
        return True

    def run(self):
        # Normalize symbol (NIFTY50 -> NIFTY, NIFTY 50 -> NIFTY, NIFTYBANK -> BANKNIFTY)
        original_symbol = self.symbol
        symbol_upper = self.symbol.upper().replace(" ", "")
        if "BANK" in symbol_upper and "NIFTY" in symbol_upper:
            self.symbol = "BANKNIFTY"
        elif "NIFTY" in symbol_upper:
            self.symbol = "NIFTY" if symbol_upper.replace("50", "") == "NIFTY" else "NIFTY"
        else:
            self.symbol = original_symbol
        if original_symbol != self.symbol:
            self.logger.info(f"Symbol normalized: {original_symbol} -> {self.symbol}")
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
                # 1. Fetch Stock Data
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

                # Use NSE_INDEX for NIFTY index
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
                df = self.client.history(symbol=self.symbol, interval="15m", exchange=exchange,
                                    start_date=start_date, end_date=end_date)

                if df.empty or len(df) < 50:
                    time.sleep(60)
                    continue

                # 2. Fetch Index Data - Use NSE_INDEX for indices (use "NIFTY" not "NIFTY 50")
                index_df = self.client.history(symbol="NIFTY", interval="15m", exchange="NSE_INDEX",
                                          start_date=start_date, end_date=end_date)

                # Fetch Sector for Sector Momentum Overlay
                sector_df = self.client.history(symbol=self.sector, interval="15m",
                                           start_date=start_date, end_date=end_date)

                # 3. Indicators
                df['roc'] = df['close'].pct_change(periods=10)

                # RSI
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs_val = gain / loss
                df['rsi'] = 100 - (100 / (1 + rs_val))

                # SMA for Trend
                df['sma50'] = df['close'].rolling(50).mean()

                last = df.iloc[-1]
                current_price = last['close']

                # Relative Strength vs NIFTY
                rs_excess = self.calculate_relative_strength(df, index_df)

                # Sector Momentum Overlay (Stock ROC vs Sector ROC)
                sector_outperformance = 0.0
                if not sector_df.empty:
                    try:
                         sector_roc = sector_df['close'].pct_change(10).iloc[-1]
                         sector_outperformance = last['roc'] - sector_roc
                    except: pass
                else:
                    sector_outperformance = 0.001 # Assume positive if missing to not block

                # News Sentiment
                sentiment = self.get_news_sentiment()

                # Manage Position via RiskManager
                if self.rm:
                    # Check Stop Loss / Trailing Stop
                    stop_hit, stop_msg = self.rm.check_stop_loss(self.symbol, current_price)
                    if stop_hit:
                        self.logger.info(stop_msg)
                        self.rm.register_exit(self.symbol, current_price)
                        time.sleep(60)
                        continue

                    # Update Trailing Stop
                    self.rm.update_trailing_stop(self.symbol, current_price)

                    # Check EOD
                    if self.rm.should_square_off_eod():
                        self.logger.info("EOD Square-off triggered.")
                        self.rm.register_exit(self.symbol, current_price)
                        time.sleep(60)
                        continue

                    # Strategy Exit: Momentum Fades (RSI < 50)
                    pos = self.rm.positions.get(self.symbol)
                    if pos:
                        if (pos['qty'] > 0 and last['rsi'] < 50):
                            self.logger.info(f"Momentum Faded (RSI < 50). Exit.")
                            self.rm.register_exit(self.symbol, current_price)
                            time.sleep(60)
                            continue

                        # Already have position, skip entry checks
                        time.sleep(60)
                        continue

                # Entry Logic
                can_trade, reason = self.rm.can_trade() if self.rm else (True, "No RM")
                if not can_trade:
                    self.logger.debug(f"Cannot trade: {reason}")
                    time.sleep(60)
                    continue

                if (last['roc'] > self.roc_threshold and
                    last['rsi'] > 55 and
                    rs_excess > 0 and
                    sector_outperformance > 0 and
                    current_price > last['sma50'] and
                    sentiment >= 0):

                    # Volume check
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * 0.5:
                        self.logger.info(f"Strong Momentum Signal (ROC: {last['roc']:.3f}, RS: {rs_excess:.3f}). BUY.")
                        if self.rm:
                            # Use risk based sizing or fixed 100 for now, but routed through RM
                            # Ideally: qty = self.rm.calculate_position_size(...)
                            qty = 100
                            self.rm.register_entry(self.symbol, qty, current_price, 'LONG')

            except Exception as e:
                self.logger.error(f"Error in ML Momentum strategy for {self.symbol}: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='ML Momentum Strategy')
    parser.add_argument('--symbol', type=str, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')
    parser.add_argument('--threshold', type=float, default=0.01, help='ROC Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')
    parser.add_argument('--logfile', type=str, help='Log file path')

    args = parser.parse_args()
    
    # Setup logging
    if args.logfile:
        logging.basicConfig(filename=args.logfile, level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)

    # Use command-line args if provided, otherwise fall back to environment variables
    symbol = args.symbol or os.getenv('SYMBOL')
    if not symbol:
        print("ERROR: --symbol argument or SYMBOL environment variable is required")
        parser.print_help()
        sys.exit(1)
    
    port = args.port or int(os.getenv('OPENALGO_PORT', '5001'))
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')

    if not api_key:
        print("ERROR: --api_key argument or OPENALGO_APIKEY environment variable is required")
        sys.exit(1)

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
