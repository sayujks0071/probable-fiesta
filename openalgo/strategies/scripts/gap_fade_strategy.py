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

try:
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
    from openalgo.strategies.utils.risk_manager import create_risk_manager
except ImportError:
    try:
        from trading_utils import APIClient, PositionManager, is_market_open
        from risk_manager import create_risk_manager
    except ImportError:
        logging.error("Could not import trading utils.")
        sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
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

        # Initialize Risk Manager
        self.rm = create_risk_manager(f"{symbol}_GapFade", "NSE", capital=200000)

    def get_previous_close(self):
        """Robustly fetch previous closing price."""
        today = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d") # Go back 7 days to cover long weekends

        # Get daily candles
        df = self.client.history(f"{self.symbol}", interval="day", start_date=start_date, end_date=today)

        if df.empty:
            logger.error("History df is empty.")
            return None

        # Filter for dates strictly before today
        # Ensure 'datetime' or 'date' column exists and is comparable
        if 'datetime' in df.columns:
            df['date_only'] = df['datetime'].dt.date
        else:
            # Fallback if history doesn't return datetime objects
            # Assuming index might be datetime
            df['date_only'] = pd.to_datetime(df.index).date

        today_date = datetime.now().date()
        prev_days = df[df['date_only'] < today_date]

        if prev_days.empty:
            logger.error("No previous day data found.")
            return None

        prev_close = prev_days.iloc[-1]['close']
        logger.info(f"Previous Close Date: {prev_days.iloc[-1]['date_only']}, Price: {prev_close}")
        return prev_close

    def execute(self):
        # 1. Check Risk Limits
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Check Failed: {reason}")
            return

        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 2. Get Previous Close
        prev_close = self.get_previous_close()
        if not prev_close:
            return

        # 3. Get Current Price (LTP)
        quote = self.client.get_quote(f"{self.symbol}", "NSE")
        if not quote or 'ltp' not in quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])
        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        # 4. Calculate Gap
        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 5. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL" # Futures Sell
            # For options: Buy PE
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY"
            option_type = "CE"

        # 6. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = 15.0
        if vix_quote and 'ltp' in vix_quote:
             vix = float(vix_quote['ltp'])

        qty = self.qty
        if vix > 30:
            qty = max(1, int(qty * 0.5))
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 7. Execute Trade (Using PositionManager to track state)
        if self.pm.has_position():
            logger.info("Already have a position. Skipping entry.")
            # Here we could implement exit logic if gap closes
            return

        logger.info(f"Executing {action} for {qty} qty.")

        # Real execution would go here using client.placesmartorder
        # For now, we update PositionManager to track it
        self.pm.update_position(qty, current_price, action)

        # Register with Risk Manager
        self.rm.register_entry(self.symbol, qty, current_price, action)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5001, help="Broker API Port")
    parser.add_argument("--loop", action="store_true", help="Run in a loop")
    args = parser.parse_args()

    api_key = os.getenv("OPENALGO_API_KEY") or "demo_key"
    client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold)

    if args.loop:
        logger.info("Running in loop mode...")
        while True:
            if is_market_open():
                strategy.execute()
            else:
                logger.info("Market closed.")

            time.sleep(300) # Check every 5 mins
    else:
        strategy.execute()

if __name__ == "__main__":
    main()
