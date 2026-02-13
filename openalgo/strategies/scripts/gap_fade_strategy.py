#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager

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
        # Using history API for last few days to be safe
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0.0
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")

        if quote and 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])
        elif not df.empty:
             # Fallback to history
             # Assuming last row is previous day if market just opened, or we check date
             # For simplicity, if quote prev close failed, we use last history close
             prev_close = df.iloc[-1]['close']

        if prev_close == 0:
             logger.error("Could not determine prev close.")
             return

        # Fetch current price again or use quote ltp
        current_price = 0.0
        if quote:
            current_price = float(quote.get('ltp', 0))

        if current_price == 0:
             logger.error("Could not fetch current price.")
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
            logger.info("Gap UP detected. Looking to FADE (Short) -> Buy PE.")
            action = "BUY"
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long) -> Buy CE.")
            action = "BUY"
            option_type = "CE"

        # 3. Check VIX for Sizing
        vix = self.client.get_vix()
        if vix is None:
             vix = 15.0 # Default

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 4. Select Option Strike (ATM)
        step = 100 if "SENSEX" in self.symbol else 50
        if "BANK" in self.symbol: step = 100

        atm = round(current_price / step) * step

        chain = self.client.get_option_chain(self.symbol)
        trading_symbol = None

        if chain:
            for item in chain:
                if item.get('strike') == atm:
                    if option_type == "CE":
                        trading_symbol = item.get('ce', {}).get('symbol')
                    else:
                        trading_symbol = item.get('pe', {}).get('symbol')
                    break

        if not trading_symbol:
            logger.warning(f"Could not resolve trading symbol for ATM {atm} {option_type}. Aborting.")
            return

        logger.info(f"Selected Trading Symbol: {trading_symbol}")

        # 5. Place Order
        resp = self.client.placesmartorder(
            strategy="GapFade",
            symbol=trading_symbol,
            action=action,
            exchange="NFO",
            price_type="MARKET",
            product="MIS",
            quantity=qty,
            position_size=qty
        )

        logger.info(f"Order Response: {resp}")

        if resp and resp.get('status') != 'error':
             self.pm.update_position(qty, current_price, action)

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
