#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "openalgo" / "strategies" / "logs" / "gap_fade.log")
    ]
)
logger = logging.getLogger("GapFadeStrategy")

class GapFadeStrategy:
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, live_mode=False):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.live_mode = live_mode
        self.pm = PositionManager(f"{symbol}_GapFade")

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 1. Get Previous Close
        # Using history API for last 2 days
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d") # Go back enough to get prev day
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        if df.empty or len(df) < 1:
            logger.error("Could not fetch history for previous close.")
            return

        # Assuming the last completed row is previous day, or if market just opened, we might have today's open
        # We need yesterday's close.
        # If we run this at 9:15, the last row in 'day' history might be yesterday.

        prev_close = df.iloc[-1]['close']
        # If the last row is today (because market started), check date
        # This logic depends on how the API returns daily candles during the day.
        # Let's assume we get prev close from quote 'ohlc' if available.

        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Some APIs provide 'close' in quote which is prev_close
        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL" # Futures Sell or PE Buy
            # For options: Buy PE
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY"
            option_type = "CE"

        # 3. Select Option Strike (ATM)
        atm = round(current_price / 50) * 50
        # Symbol format varies, this is a placeholder. In real live mode, use SymbolResolver or explicit format
        # For NIFTY Options: NIFTY24FEB22000CE
        expiry_str = today.strftime('%y%b').upper()
        strike_symbol = f"{self.symbol}{expiry_str}{atm}{option_type}"

        logger.info(f"Signal: Buy {option_type} at {atm} (Gap Fade). Symbol: {strike_symbol}")

        # 4. Check VIX for Sizing (inherited from general rules)
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order
        if self.live_mode:
            logger.info(f"LIVE MODE: Placing Smart Order for {strike_symbol} qty {qty}")
            response = self.client.placesmartorder(
                strategy="GapFade",
                symbol=strike_symbol,
                action="BUY",
                exchange="NFO",
                price_type="MARKET",
                product="MIS",
                quantity=qty,
                position_size=qty
            )
            logger.info(f"Order Response: {response}")

            if response and response.get("status") == "success":
                self.pm.update_position(qty, current_price, "BUY") # Using underlying price as proxy for entry tracking if option price unknown
        else:
            logger.info(f"SIMULATION: Executing {option_type} Buy for {qty} qty.")
            self.pm.update_position(qty, current_price, "BUY")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, help="Broker API Port (default: env OPENALGO_PORT or 5002)")
    parser.add_argument("--live", action="store_true", help="Enable Live Trading")
    args = parser.parse_args()

    port = args.port or int(os.getenv("OPENALGO_PORT", "5002"))
    api_key = os.getenv("OPENALGO_API_KEY", "demo_key")

    client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, live_mode=args.live)
    strategy.execute()

if __name__ == "__main__":
    main()
