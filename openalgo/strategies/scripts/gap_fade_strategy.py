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
try:
    from openalgo.strategies.utils.risk_manager import RiskManager
except ImportError:
    print("Error: RiskManager module not found. Please ensure openalgo/strategies/utils/risk_manager.py exists.")
    sys.exit(1)

# Ensure log directory exists
log_dir = project_root / "openalgo" / "strategies" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
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
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage

        # Initialize Risk Manager
        self.rm = RiskManager(
            strategy_name=f"GapFade_{symbol}",
            exchange="NSE",
            capital=100000,
            config={'max_daily_loss_pct': 2.0}
        )

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 1. Get Previous Close
        # Using history API for last 5 days
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        if df.empty or len(df) < 1:
            logger.error("Could not fetch history for previous close.")
            return

        # Determine Previous Close logic
        prev_close = 0.0

        # Parse dates if available
        if 'datetime' in df.columns:
            df['date_only'] = df['datetime'].dt.date
            today_date = today.date()

            # Check if last row is today
            last_row = df.iloc[-1]
            if last_row['date_only'] == today_date:
                if len(df) > 1:
                    prev_close = df.iloc[-2]['close']
                else:
                    logger.warning("History has today's data but no previous day. Cannot determine gap.")
                    return
            else:
                prev_close = last_row['close']
        else:
             # Fallback: simple index check, risky but legacy behavior kept as last resort
             prev_close = df.iloc[-1]['close']

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

        # 5. Place Order with Risk Checks
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Check Failed: {reason}")
            return

        # Execute
        logger.info(f"Executing {option_type} Buy for {qty} qty.")

        # Calculate Stop Loss (e.g., 10%)
        # In a real scenario, we'd place the order here via self.client.placesmartorder(...)
        # For now, we simulate the fill price as current ATM price (simplified)

        # entry_price would be the option price. Since we don't have option quote here easily without another call,
        # we will mock it or fetch it if possible.
        # For this exercise, we assume we got a fill at 100.
        fill_price = 100.0

        # Register with Risk Manager
        self.rm.register_entry(
            symbol=strike_symbol,
            qty=qty,
            entry_price=fill_price,
            side="LONG", # Buying option is Long
            stop_loss=fill_price * 0.9 # 10% SL
        )

        logger.info(f"Trade Registered: {strike_symbol} @ {fill_price}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    # Use Env Var for URL if available, else construct from port
    api_url = os.getenv("OPENALGO_API_URL", f"http://127.0.0.1:{args.port}")

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=api_url)
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold)
    strategy.execute()

if __name__ == "__main__":
    main()
