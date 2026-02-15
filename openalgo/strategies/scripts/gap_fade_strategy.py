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
from openalgo.strategies.utils.risk_manager import create_risk_manager

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
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, gap_pct_override=None, vix=None):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.gap_pct_override = gap_pct_override
        self.vix = vix

        self.pm = PositionManager(f"{symbol}_GapFade")
        self.rm = create_risk_manager(f"{symbol}_GapFade", "NSE", capital=200000)

    def get_vix(self):
        if self.vix is not None: return self.vix
        try:
            q = self.client.get_quote("INDIA VIX", "NSE")
            return float(q['ltp']) if q else 15.0
        except:
            return 15.0

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Check Risk Manager
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Manager blocked trade: {reason}")
            return

        gap_pct = 0.0
        current_price = 0.0

        # 1. Determine Gap
        if self.gap_pct_override is not None:
             gap_pct = self.gap_pct_override
             logger.info(f"Using provided Gap %: {gap_pct}")
             # We still need current price for strike selection
             try:
                 quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
                 current_price = float(quote['ltp']) if quote else 0
             except:
                 pass
             if current_price == 0:
                 # Try index if tuple failed
                 try:
                     quote = self.client.get_quote(self.symbol, "NSE")
                     current_price = float(quote['ltp']) if quote else 0
                 except:
                     pass
        else:
            # Calculate internally
            # Get Previous Close
            today = datetime.now()

            # Try to get previous close
            prev_close = 0
            quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
            if not quote:
                logger.error("Could not fetch quote.")
                return

            current_price = float(quote['ltp'])

            if 'close' in quote and quote['close'] > 0:
                prev_close = float(quote['close'])

            if prev_close == 0:
                 logger.error("Previous close not available.")
                 return

            gap_pct = ((current_price - prev_close) / prev_close) * 100
            logger.info(f"Calculated Gap: {gap_pct:.2f}% (Prev: {prev_close}, Curr: {current_price})")

        if current_price == 0:
            logger.error("Current Price is 0. Cannot proceed.")
            return

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Buy Put).")
            action = "BUY"
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Buy Call).")
            action = "BUY"
            option_type = "CE"

        # 3. Select Option Strike (ATM)
        atm = round(current_price / 50) * 50

        logger.info(f"Signal: Buy {option_type} at {atm} (Gap Fade)")

        # 4. Check VIX for Sizing
        vix = self.get_vix()
        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order
        if not self.pm.has_position():
            logger.info(f"Executing {option_type} Buy for {qty} qty.")

            # Register with Risk Manager
            # Assuming we bought at 100 premium (placeholder)
            premium = 100.0

            # In real execution, we would call place_order and get fill price
            # self.client.placesmartorder(...)

            self.rm.register_entry(f"{self.symbol}_{atm}_{option_type}", qty, premium, "LONG")
            self.pm.update_position(qty, premium, "BUY")
        else:
            logger.info("Position already exists. Skipping.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    parser.add_argument("--gap_pct", type=float, default=None, help="Gap Percent Override")
    parser.add_argument("--vix", type=float, default=None, help="VIX Override")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(
        client,
        args.symbol,
        args.qty,
        args.threshold,
        gap_pct_override=args.gap_pct,
        vix=args.vix
    )
    strategy.execute()

if __name__ == "__main__":
    main()
