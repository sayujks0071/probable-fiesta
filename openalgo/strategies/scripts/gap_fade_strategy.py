#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
import pandas as pd
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
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.pm = PositionManager(f"{symbol}_GapFade")

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 1. Get Previous Close
        # Using history API for last 5 days to ensure we get prev close
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        # Note: If running pre-market, today's candle doesn't exist yet.
        # If running at 9:15, today's candle exists.
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0
        if not df.empty and len(df) >= 1:
             # If last row date is today, use previous row
             # Check if last row date is today
             last_date = pd.to_datetime(df.iloc[-1]['datetime']).date()
             if last_date == today.date():
                 if len(df) >= 2:
                     prev_close = df.iloc[-2]['close']
                 else:
                     logger.error("Not enough history for prev close.")
                     return
             else:
                 prev_close = df.iloc[-1]['close']
        else:
             # Fallback to Quote 'close' (Previous Close)
             quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
             if quote and 'close' in quote:
                 prev_close = float(quote['close'])

        if prev_close == 0:
            # Try symbol directly
            quote = self.client.get_quote(self.symbol, "NSE")
            if quote and 'close' in quote:
                 prev_close = float(quote['close'])

        if prev_close == 0:
            logger.error("Could not determine previous close.")
            return

        # Get Current Price (Spot)
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        current_price = float(quote['ltp']) if quote and 'ltp' in quote else 0
        if current_price == 0:
             quote = self.client.get_quote(self.symbol, "NSE")
             current_price = float(quote['ltp']) if quote and 'ltp' in quote else 0

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        if prev_close == 0: return

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
            logger.info("Gap UP detected. Looking to FADE (Buy Put).")
            option_type = "PE"
            action = "BUY"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Buy Call).")
            option_type = "CE"
            action = "BUY"

        # 3. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote and 'ltp' in vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 4. Select Option Strike (ATM)
        # Select nearest 50 strike
        atm = round(current_price / 50) * 50

        # Construct Symbol (Simplified, in real usage need to resolve symbol code e.g. NIFTY24FEB22000CE)
        # We'll rely on client.placesmartorder taking strategy parameters or resolving it if we pass "NIFTY 22000 CE" format?
        # The API placesmartorder usually takes a tradingsymbol.
        # We need to find the tradingsymbol for ATM + option_type + nearest expiry.

        # Fetch Chain to find symbol
        chain = self.client.get_option_chain(self.symbol)
        found_symbol = None
        if chain:
            # Find ATM strike in chain
            # Chain usually has 'strike', 'ce': {'symbol': ...}, 'pe': {'symbol': ...}
            # Find item with strike == atm
            for item in chain:
                if item.get('strike') == atm:
                    if option_type == "CE":
                        found_symbol = item.get('ce', {}).get('symbol') or item.get('ce_symbol')
                    else:
                        found_symbol = item.get('pe', {}).get('symbol') or item.get('pe_symbol')
                    break

        if not found_symbol:
            # Fallback to constructing generic if API handles it, or fail
            logger.warning(f"Could not find exact symbol for Strike {atm} {option_type}. Using generic format.")
            # NIFTY 27FEB25 23000 CE - format depends on broker
            # For now, we log failure to find symbol and return to avoid bad orders
            logger.error("Cannot execute without valid trading symbol.")
            return

        logger.info(f"Selected Symbol: {found_symbol} (Strike {atm})")

        # 5. Place Order
        # placesmartorder(strategy, symbol, action, exchange, price_type, product, quantity, position_size)
        resp = self.client.placesmartorder(
            strategy="GapFade",
            symbol=found_symbol,
            action=action,
            exchange="NFO",
            price_type="MARKET",
            product="MIS",
            quantity=qty,
            position_size=qty
        )

        logger.info(f"Order Response: {resp}")

        if resp.get('status') == 'success':
            self.pm.update_position(qty, current_price, action)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_APIKEY") or os.getenv("OPENALGO_API_KEY", "dummy"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold)
    strategy.execute()

if __name__ == "__main__":
    main()
