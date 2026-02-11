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

from openalgo.strategies.utils.trading_utils import APIClient, is_market_open
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
        self.external_gap_pct = gap_pct
        self.rm = RiskManager(f"{symbol}_GapFade", exchange="NSE", capital=100000)

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Check Risk Manager
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Manager blocked trade: {reason}")
            return

        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Determine Gap
        today = datetime.now()
        if self.external_gap_pct is not None:
             gap_pct = self.external_gap_pct
             logger.info(f"Using external Gap: {gap_pct:.2f}%")
        else:
            # Internal calculation
            # Using history API for last 2 days
            start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")

            # Get daily candles
            df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)
            prev_close = 0

            if not df.empty and len(df) >= 1:
                 prev_close = df.iloc[-1]['close']

            if 'close' in quote and quote['close'] > 0:
                prev_close = float(quote['close'])

            if prev_close == 0:
                logger.error("Could not determine previous close.")
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

        # Register Entry with Risk Manager
        price = 100.0 # Mock option price
        sl_price = self.rm.calculate_stop_loss(price, "LONG", stop_pct=10.0)

        self.rm.register_entry(
            symbol=f"{self.symbol}_{atm}_{option_type}",
            qty=qty,
            entry_price=price,
            side="LONG",
            stop_loss=sl_price
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    parser.add_argument("--gap_pct", type=float, default=None, help="External Gap Pct")
    args, unknown = parser.parse_known_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, gap_pct=args.gap_pct)
    strategy.execute()

if __name__ == "__main__":
    main()
