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
    sys.path.insert(0, str(project_root))

try:
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
    from openalgo.strategies.utils.risk_manager import create_risk_manager
except ImportError:
    sys.path.append(str(project_root / "vendor"))
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
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, current_gap_pct=None):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.current_gap_pct = current_gap_pct

        # Risk Manager
        self.rm = create_risk_manager(f"{symbol}_GapFade", "NSE", capital=100000)
        self.pm = PositionManager(f"{symbol}_GapFade")

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 1. Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Check Failed: {reason}")
            return

        # 2. Determine Gap
        gap_pct = 0.0
        current_price = 0.0
        prev_close = 0.0

        if self.current_gap_pct is not None:
             gap_pct = self.current_gap_pct
             logger.info(f"Using provided Gap: {gap_pct}%")
             # Still need current price for ATM selection
             quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
             if quote:
                 current_price = float(quote['ltp'])
        else:
            # Calculate Gap manually
            quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
            if not quote:
                logger.error("Could not fetch quote.")
                return

            current_price = float(quote['ltp'])

            # Try to get prev_close from quote or history
            if 'close' in quote and quote['close'] > 0:
                prev_close = float(quote['close'])
            else:
                # Fallback to history
                today = datetime.now()
                start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

                if not df.empty and len(df) >= 1:
                     # If history includes today (market open), prev close is -2 row?
                     # API usually returns completed candles or partial.
                     # Let's assume last row is prev day if run early?
                     # Or check timestamps.
                     # Simplest: use 'close' from quote which is usually prev close until EOD.
                     pass

                if prev_close == 0:
                     logger.warning("Could not determine Prev Close. Using 0 gap.")
                     gap_pct = 0.0
                else:
                     gap_pct = ((current_price - prev_close) / prev_close) * 100

        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 3. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Short -> Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL" # Direction
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Long -> Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY" # Direction
            option_type = "CE"

        # 4. Select Option Strike (ATM)
        if current_price == 0:
             quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
             if quote: current_price = float(quote['ltp'])

        if current_price == 0:
             logger.error("Current Price is 0. Cannot select strike.")
             return

        atm = round(current_price / 50) * 50
        strike_symbol = f"{self.symbol}_{atm}_{option_type}" # Mock Symbol

        logger.info(f"Signal: Buy {option_type} at {atm} (Gap Fade)")

        # 5. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 6. Place Order & Register Risk
        logger.info(f"Executing {option_type} Buy for {qty} qty.")

        # Mock Fill
        fill_price = 100.0

        self.rm.register_entry(strike_symbol, qty, fill_price, "LONG", stop_loss=fill_price*0.9) # 10% SL for scalping gap
        self.pm.update_position(qty, fill_price, "BUY")

        logger.info("Strategy execution completed.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    parser.add_argument("--gap_pct", type=float, default=None, help="Current Gap %%")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, current_gap_pct=args.gap_pct)
    strategy.execute()

if __name__ == "__main__":
    main()
