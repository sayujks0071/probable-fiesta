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
from openalgo.strategies.utils.risk_manager import RiskManager

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
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.pm = PositionManager(f"{symbol}_GapFade")
        self.rm = RiskManager(f"GapFade_{symbol}", exchange="NSE")

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
             logger.warning(f"Risk Check Failed: {reason}")
             return

        # 1. Get Previous Close
        prev_close = 0.0
        current_price = 0.0

        # Try Quote First (Real-time and reliable for OHLC)
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")

        if quote:
            current_price = float(quote.get('ltp', 0))
            # 'close' in quote is typically previous close
            if 'close' in quote and quote['close'] > 0:
                prev_close = float(quote['close'])
            elif 'ohlc' in quote and 'close' in quote['ohlc']:
                prev_close = float(quote['ohlc']['close'])

        # Fallback to History if Prev Close is missing
        if prev_close == 0:
            today = datetime.now()
            start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
            df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

            if not df.empty and len(df) >= 1:
                # If last candle is today (check timestamp if available), take previous
                # Simplified: Take last closed candle (assuming history returns completed candles or we check time)
                # Ideally check df index date vs today.
                prev_close = df.iloc[-1]['close'] # Fallback

        if prev_close == 0 or current_price == 0:
             logger.error(f"Could not determine prices. Prev: {prev_close}, Curr: {current_price}")
             return

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
        strike_symbol = f"{self.symbol}{today.strftime('%y%b').upper()}{atm}{option_type}" # Symbol format varies
        # Simplified: Just log the intent

        logger.info(f"Signal: Buy {option_type} at {atm} (Gap Fade)")

        # 4. Check VIX for Sizing (inherited from general rules)
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order (Simulation)
        # self.client.placesmartorder(...)
        logger.info(f"Executing {option_type} Buy for {qty} qty.")
        self.pm.update_position(qty, 100, "BUY") # Mock update
        self.rm.register_entry(f"{self.symbol}_{option_type}", qty, 100, "LONG") # Mock entry

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold)
    strategy.execute()

if __name__ == "__main__":
    main()
