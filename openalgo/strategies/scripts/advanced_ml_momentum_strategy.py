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
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).resolve().parent
strategies_dir = script_dir.parent
utils_dir = strategies_dir / 'utils'
project_root = strategies_dir.parent.parent

if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

if str(utils_dir) not in sys.path:
    sys.path.append(str(utils_dir))

try:
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
except ImportError:
    # Fallback for standalone execution
    try:
        from trading_utils import APIClient, PositionManager, is_market_open
    except ImportError:
        logging.error("Could not import trading_utils. Check python path.")
        sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MLMomentum")

class MLMomentumStrategy:
    def __init__(self, symbol, api_key, port, threshold=0.01, stop_pct=1.0, sector='NIFTY 50', vol_multiplier=0.5):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)
        self.logger = logging.getLogger(f"MLMomentum_{symbol}")
        self.pm = PositionManager(symbol) if PositionManager else None

        self.roc_threshold = threshold
        self.stop_pct = stop_pct
        self.sector = sector
        self.vol_multiplier = vol_multiplier

    def calculate_indicators(self, df):
        """Calculate technical indicators."""
        df = df.copy()
        # ROC
        df['roc'] = df['close'].pct_change(periods=10)

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs_val = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs_val))

        # SMA for Trend
        df['sma50'] = df['close'].rolling(50).mean()

        return df

    def calculate_signal(self, df, index_df=None, sector_df=None):
        """
        Calculate signal for backtesting and live execution.
        Returns: (Action, Quantity_Multiplier, Metadata)
        """
        if df.empty or len(df) < 50:
            return 'HOLD', 0.0, {}

        df = self.calculate_indicators(df)

        last = df.iloc[-2] # Use completed candle
        current = df.iloc[-1]

        # We use the completed candle for signal generation to avoid repainting
        # But we execute at current price

        # Relative Strength vs NIFTY
        rs_excess = 0.0
        if index_df is not None and not index_df.empty:
            try:
                # Align timestamps roughly by index
                last_idx_ts = index_df.index[-2] if len(index_df) > 1 else index_df.index[-1]
                # Simple ROC comparison
                stock_roc = last['roc']
                index_roc = index_df['close'].pct_change(10).iloc[-2]
                rs_excess = stock_roc - index_roc
            except Exception:
                pass

        # Sector Momentum Overlay
        sector_outperformance = 0.0
        if sector_df is not None and not sector_df.empty:
            try:
                sector_roc = sector_df['close'].pct_change(10).iloc[-2]
                sector_outperformance = last['roc'] - sector_roc
            except Exception:
                pass

        # Entry Logic
        # ROC > Threshold
        # RSI > 55
        # Price > SMA50 (Uptrend)

        # Optional: RS checks (only if data provided)
        rs_condition = True
        if index_df is not None:
            rs_condition = rs_excess > 0

        sector_condition = True
        if sector_df is not None:
            sector_condition = sector_outperformance > 0

        # Volume check
        avg_vol = df['volume'].rolling(20).mean().iloc[-2]
        vol_condition = last['volume'] > avg_vol * self.vol_multiplier

        if (last['roc'] > self.roc_threshold and
            last['rsi'] > 55 and
            last['close'] > last['sma50'] and
            rs_condition and
            sector_condition and
            vol_condition):

            return 'BUY', 1.0, {
                'roc': last['roc'],
                'rsi': last['rsi'],
                'rs_excess': rs_excess
            }

        # Exit Logic (Simple RSI Fade)
        if last['rsi'] < 50:
             return 'SELL', 1.0, {'reason': 'Momentum Faded'}

        return 'HOLD', 0.0, {}

    def run(self):
        # Normalize symbol
        original_symbol = self.symbol
        symbol_upper = self.symbol.upper().replace(" ", "")
        if "BANK" in symbol_upper and "NIFTY" in symbol_upper:
            self.symbol = "BANKNIFTY"
        elif "NIFTY" in symbol_upper:
            self.symbol = "NIFTY"
        else:
            self.symbol = original_symbol

        self.logger.info(f"Starting ML Momentum Strategy for {self.symbol} (Sector: {self.sector})")

        while True:
            try:
                if not is_market_open():
                    self.logger.info("Market Closed. Sleeping...")
                    time.sleep(300)
                    continue

                # 1. Fetch Stock Data
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
                df = self.client.history(symbol=self.symbol, interval="15m", exchange=exchange,
                                    start_date=start_date, end_date=end_date)

                if df.empty or len(df) < 50:
                    time.sleep(60)
                    continue

                # 2. Fetch Index Data (Optional but recommended)
                index_df = self.client.history(symbol="NIFTY", interval="15m", exchange="NSE_INDEX",
                                          start_date=start_date, end_date=end_date)

                # 3. Fetch Sector Data (Optional)
                sector_df = self.client.history(symbol=self.sector, interval="15m",
                                           start_date=start_date, end_date=end_date)

                # 4. Calculate Signal
                signal, qty_mult, meta = self.calculate_signal(df, index_df, sector_df)

                current_price = df.iloc[-1]['close']

                # 5. Execute
                if self.pm:
                    has_pos = self.pm.has_position()

                    # Stop Loss Check
                    if has_pos and self.pm.position > 0:
                        entry = self.pm.entry_price
                        if current_price < entry * (1 - self.stop_pct/100):
                             self.logger.info(f"Stop Loss Hit. Current: {current_price}, Entry: {entry}")
                             self.pm.update_position(abs(self.pm.position), current_price, 'SELL')
                             continue

                    if signal == 'BUY' and not has_pos:
                        self.logger.info(f"BUY Signal: {meta}")
                        self.pm.update_position(100, current_price, 'BUY') # Fixed Qty 100 for now

                    elif signal == 'SELL' and has_pos and self.pm.position > 0:
                        self.logger.info(f"SELL Signal (Exit): {meta}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

            except Exception as e:
                self.logger.error(f"Error in ML Momentum strategy: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='ML Momentum Strategy')
    parser.add_argument('--symbol', type=str, help='Stock Symbol')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')
    parser.add_argument('--threshold', type=float, default=0.01, help='ROC Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')

    args = parser.parse_args()
    
    symbol = args.symbol or os.getenv('SYMBOL')
    if not symbol:
        print("ERROR: --symbol argument or SYMBOL environment variable is required")
        sys.exit(1)
    
    port = args.port or int(os.getenv('OPENALGO_PORT', '5001'))
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("ERROR: --api_key or OPENALGO_APIKEY env var required")
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
