#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
import pytz
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, SmartOrder
from openalgo.strategies.utils.risk_manager import RiskManager

# Configure logging
log_dir = project_root / "openalgo" / "strategies" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "gap_fade.log")
    ]
)
logger = logging.getLogger("GapFadeStrategy")

class GapFadeStrategy:
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, capital=100000):
        self.client = api_client
        self.symbol = symbol
        self.base_qty = qty
        self.gap_threshold = gap_threshold # Percentage

        # Initialize Helpers
        self.so = SmartOrder(self.client)
        self.rm = RiskManager(f"{symbol}_GapFade", exchange="NSE", capital=capital)

        # Ensure PM is synced with RM (conceptually)
        self.pm = PositionManager(f"{symbol}_GapFade")

    def get_market_data(self):
        """Fetch Previous Close and Current Price."""
        try:
            # 1. Get History (Last 7 days) to find prev close
            tz = pytz.timezone('Asia/Kolkata')
            today_date = datetime.now(tz).date()
            start_date = (today_date - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = today_date.strftime("%Y-%m-%d")

            # Fetch daily candles
            df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

            if df.empty:
                logger.error("History fetch failed.")
                return None, None

            # Handle datetime column
            if 'datetime' in df.columns:
                df['date'] = pd.to_datetime(df['datetime']).dt.date
            else:
                # If timestamp or index
                pass # APIClient usually ensures datetime

            # Filter out today's candle if present
            # If the last row date is today, exclude it
            if not df.empty:
                last_date = pd.to_datetime(df.iloc[-1]['datetime']).date()
                if last_date >= today_date:
                    df = df.iloc[:-1]

            if df.empty:
                logger.error("No historical data prior to today.")
                return None, None

            prev_close = float(df.iloc[-1]['close'])

            # 2. Get Current Price (Quote)
            quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
            if not quote or 'ltp' not in quote:
                logger.error("Quote fetch failed.")
                return None, None

            current_price = float(quote['ltp'])

            return prev_close, current_price

        except Exception as e:
            logger.error(f"Market Data Error: {e}", exc_info=True)
            return None, None

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 1. Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Check Failed: {reason}")
            return

        # 2. Market Data
        prev_close, current_price = self.get_market_data()
        if not prev_close or not current_price:
            return

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        # 3. Calculate Gap
        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 4. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Short Future or Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Buy PE).")
            option_type = "PE"
            action = "BUY"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Long Future or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Buy CE).")
            option_type = "CE"
            action = "BUY"

        # 5. Select Option Strike (ATM)
        atm = round(current_price / 50) * 50
        now = datetime.now()
        # Simple symbol construction (User should replace with SymbolResolver)
        strike_symbol = f"{self.symbol}{now.strftime('%y%b').upper()}{atm}{option_type}"
        logger.info(f"Selected Symbol: {strike_symbol}")

        # 6. Check VIX for Sizing
        vix = self.client.get_vix() or 15.0

        qty = self.base_qty
        if vix > 25:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 7. Place Order via SmartOrder
        # Check if we already have a position in this symbol
        open_positions = self.rm.get_open_positions()
        # Crude check: if we hold anything starting with the index symbol
        for pos_sym in open_positions:
            if self.symbol in pos_sym:
                logger.info(f"Position {pos_sym} already exists. Skipping.")
                return

        logger.info(f"Executing {action} {strike_symbol} for {qty} qty.")

        response = self.so.place_adaptive_order(
            strategy="GapFade",
            symbol=strike_symbol,
            action=action,
            exchange="NFO",
            quantity=qty,
            urgency="HIGH"
        )

        if response and response.get('status') == 'success':
            # Register with Risk Manager
            fill_price = float(response.get('average_price', current_price))
            if fill_price == 0: fill_price = current_price # Safety

            logger.info(f"Order Success. Filled at {fill_price}")

            self.rm.register_entry(
                symbol=strike_symbol,
                qty=qty,
                entry_price=fill_price,
                side="LONG", # Options Buy
                stop_loss=None # Auto-calc
            )

            self.pm.update_position(qty, fill_price, action)
        else:
            logger.error(f"Order Execution Failed: {response}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--capital", type=float, default=100000, help="Trading Capital")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    api_key = os.getenv("OPENALGO_API_KEY") or "DEMO_KEY"
    client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{args.port}")

    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, args.capital)
    strategy.execute()

if __name__ == "__main__":
    main()
