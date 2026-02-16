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
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, gap_pct=None):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.gap_pct = gap_pct

        self.pm = PositionManager(f"{symbol}_GapFade")
        self.rm = RiskManager("GapFade", "NSE", 200000) # 2 Lakh capital

    def get_gap_pct(self):
        if self.gap_pct is not None and self.gap_pct != 0.0:
            return self.gap_pct

        # 1. Get Previous Close
        # Using history API for last 2 days
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d") # Go back enough to get prev day
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0
        current_price = 0

        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return 0.0

        current_price = float(quote['ltp'])

        # Some APIs provide 'close' in quote which is prev_close
        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])
        elif not df.empty and len(df) >= 1:
             prev_close = df.iloc[-1]['close']

        if prev_close == 0:
            return 0.0

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        calc_gap = ((current_price - prev_close) / prev_close) * 100
        return calc_gap

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Manager blocked trade: {reason}")
            return

        gap_pct = self.get_gap_pct()
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
            action = "BUY"
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY"
            option_type = "CE"

        # 3. Select Option Strike (ATM)
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        current_price = float(quote['ltp']) if quote else 0

        atm = round(current_price / 50) * 50
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

        # Register with Risk Manager
        # Assume entry price is approx 100 for mock
        self.rm.register_entry(f"{self.symbol}_{option_type}_{atm}", qty, 100.0, "LONG")

        logger.info("Trade executed and registered with RiskManager.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--gap_pct", type=float, default=None, help="Gap %% Override")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, gap_pct=args.gap_pct)
    strategy.execute()

if __name__ == "__main__":
    main()
