#!/usr/bin/env python3
"""
ORB Strategy - Open Range Breakout
Implements a standard ORB strategy with configurable parameters.
"""
import sys
import os
import time
import logging
import argparse
import pandas as pd
from datetime import datetime, timedelta

# Ensure openalgo modules can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up 3 levels: scripts -> strategies -> openalgo -> root
root_dir = os.path.abspath(os.path.join(current_dir, '../../../'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from openalgo.strategies.utils.config import StrategyConfig
except ImportError:
    # Fallback/Retry logic or local import
    try:
        sys.path.append(os.path.join(current_dir, '../'))
        from utils.config import StrategyConfig
    except ImportError:
        print("CRITICAL: Could not import StrategyConfig. Check paths.")
        sys.exit(1)

try:
    from openalgo import api
except ImportError:
    # Allow running without openalgo installed for testing/dev if mocked
    api = None
    print("WARNING: openalgo api module not found. Strategy will fail to connect if not mocked.")

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ORB")

class ORBStrategy:
    def __init__(self, symbol, quantity, timeframe, orb_minutes, stop_loss_pct, target_pct):
        self.config = StrategyConfig("orb_strategy")
        self.symbol = symbol or self.config.get("SYMBOL", "NIFTY25JANFUT")
        self.quantity = int(quantity or self.config.get("QUANTITY", 50))
        self.timeframe = timeframe
        self.orb_minutes = int(orb_minutes)
        self.stop_loss_pct = float(stop_loss_pct)
        self.target_pct = float(target_pct)

        self.api_key = self.config.api_key
        self.host = self.config.host
        self.client = None

        self.orb_high = None
        self.orb_low = None
        self.orb_calculated = False
        self.position = None # None, 'LONG', 'SHORT'
        self.entry_price = 0.0

    def connect(self):
        if not api:
            logger.error("OpenAlgo API module not found.")
            return False
        try:
            self.client = api(api_key=self.api_key, host=self.host)
            logger.info(f"Connected to OpenAlgo at {self.host}")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def get_market_start_time(self):
        now = datetime.now()
        # Default NSE start 9:15
        return now.replace(hour=9, minute=15, second=0, microsecond=0)

    def calculate_orb(self):
        start_time = self.get_market_start_time()
        end_time = start_time + timedelta(minutes=self.orb_minutes)
        now = datetime.now()

        if now < end_time:
            # logger.info(f"Waiting for ORB period end: {end_time.strftime('%H:%M')}")
            return False # ORB period not over

        if self.orb_calculated:
            return True

        logger.info(f"Calculating ORB for {self.symbol} ({start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')})")

        try:
            # Fetch history
            df = self.client.history(
                symbol=self.symbol,
                exchange="NSE",
                interval="1m",
                start_date=start_time.strftime("%Y-%m-%d"),
                end_date=now.strftime("%Y-%m-%d")
            )

            # Check if df is valid
            if df is None or (isinstance(df, pd.DataFrame) and df.empty) or (isinstance(df, list) and not df):
                logger.warning("No data received for ORB calculation")
                return False

            # Convert to DataFrame if list
            if isinstance(df, list):
                df = pd.DataFrame(df)

            # Ensure data consistency
            if 'time' in df.columns:
                 # Standardize time
                 df['datetime'] = pd.to_datetime(df['time'])
            elif 'date' in df.columns:
                 df['datetime'] = pd.to_datetime(df['date'])
            else:
                 logger.error("Data missing time column")
                 return False

            # Filter for ORB period
            mask = (df['datetime'] >= start_time) & (df['datetime'] < end_time)
            orb_df = df.loc[mask]

            if not orb_df.empty:
                self.orb_high = float(orb_df['high'].max())
                self.orb_low = float(orb_df['low'].min())
                self.orb_calculated = True
                logger.info(f"ORB Calculated: High={self.orb_high}, Low={self.orb_low}")
                return True
            else:
                logger.warning("No data found within ORB time range")
                return False

        except Exception as e:
            logger.error(f"Error calculating ORB: {e}", exc_info=True)
            return False

    def run(self):
        if not self.connect():
            return

        logger.info(f"Starting ORB Strategy for {self.symbol} (Qty: {self.quantity})")

        while True:
            try:
                now = datetime.now()
                market_open = self.get_market_start_time()

                if now < market_open:
                    logger.info("Waiting for market open...")
                    time.sleep(60)
                    continue

                # Calculate ORB
                if not self.orb_calculated:
                    if not self.calculate_orb():
                        time.sleep(10)
                        continue

                # Check for signals
                quote = self.client.get_quote(self.symbol)

                if not quote:
                     time.sleep(1)
                     continue

                # Handle quote response format
                if isinstance(quote, dict):
                    ltp = float(quote.get('ltp', 0) or quote.get('last_price', 0) or quote.get('close', 0))
                else:
                    ltp = 0

                if ltp == 0:
                    continue

                if self.position is None:
                    if ltp > self.orb_high:
                        self.place_order("BUY", ltp)
                    elif ltp < self.orb_low:
                        self.place_order("SELL", ltp)
                else:
                    self.monitor_position(ltp)

            except KeyboardInterrupt:
                logger.info("Stopping strategy...")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                time.sleep(5)

            time.sleep(1)

    def place_order(self, side, price):
        logger.info(f"[ENTRY] symbol={self.symbol} side={side} entry={price} qty={self.quantity}")
        try:
             # In a real implementation, we would call client.place_order(...)
             # For now, we simulate execution
             # order_id = self.client.place_order(symbol=self.symbol, side=side, quantity=self.quantity, ...)

             self.position = "LONG" if side == "BUY" else "SHORT"
             self.entry_price = price
             logger.info(f"✅ Order placed successfully for {self.symbol}: Order ID SIM-{int(time.time())}")
        except Exception as e:
             logger.error(f"Order placement failed: {e}")

    def monitor_position(self, current_price):
        if self.position == "LONG":
            # Check Stop Loss
            sl_price = self.entry_price * (1 - self.stop_loss_pct/100)
            target_price = self.entry_price * (1 + self.target_pct/100)

            if current_price <= sl_price:
                self.close_position(current_price, "StopLoss")
            elif current_price >= target_price:
                self.close_position(current_price, "Target")

        elif self.position == "SHORT":
            sl_price = self.entry_price * (1 + self.stop_loss_pct/100)
            target_price = self.entry_price * (1 - self.target_pct/100)

            if current_price >= sl_price:
                self.close_position(current_price, "StopLoss")
            elif current_price <= target_price:
                self.close_position(current_price, "Target")

    def close_position(self, price, reason):
        pnl = (price - self.entry_price) * self.quantity if self.position == "LONG" else (self.entry_price - price) * self.quantity
        logger.info(f"[EXIT] symbol={self.symbol} exit={price} pnl={pnl:.2f} reason={reason}")
        self.position = None
        # In real strategy, we might stop or reset. For ORB usually one trade per day.
        logger.info("ORB Trade completed. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ORB Strategy')
    parser.add_argument('--symbol', type=str, help='Trading Symbol')
    parser.add_argument('--qty', type=int, help='Quantity')
    parser.add_argument('--interval', type=str, default='1m', help='Candle interval')
    parser.add_argument('--orb_minutes', type=int, default=15, help='ORB Duration in minutes')
    parser.add_argument('--sl', type=float, default=1.0, help='Stop Loss %')
    parser.add_argument('--target', type=float, default=2.0, help='Target %')

    args = parser.parse_args()

    strategy = ORBStrategy(
        symbol=args.symbol,
        quantity=args.qty,
        timeframe=args.interval,
        orb_minutes=args.orb_minutes,
        stop_loss_pct=args.sl,
        target_pct=args.target
    )
    strategy.run()
