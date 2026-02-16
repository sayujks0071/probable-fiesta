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

# Import RiskManager
try:
    from openalgo.strategies.utils.risk_manager import RiskManager
except ImportError:
    try:
        sys.path.insert(0, str(project_root / "openalgo" / "strategies" / "utils"))
        from risk_manager import RiskManager
    except ImportError:
        RiskManager = None

# Configure logging
log_dir = project_root / "openalgo" / "log" / "strategies"
log_dir.mkdir(parents=True, exist_ok=True)

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
        self.pm = PositionManager(f"{symbol}_GapFade")

        if RiskManager:
            self.rm = RiskManager(strategy_name=f"GapFade_{symbol}", exchange="NSE", capital=200000)
        else:
            self.rm = None
            logger.warning("RiskManager not available")

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Check RiskManager circuit breaker first
        if self.rm:
            can_trade, reason = self.rm.can_trade()
            if not can_trade:
                logger.warning(f"RiskManager blocked trade: {reason}")
                return

        # 1. Get Previous Close
        # Using history API for last 2 days
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d") # Go back enough to get prev day
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0.0
        if not df.empty:
             # Look for yesterday's close
             # Assuming last row is potentially today if market open, so check dates or take -2
             # Simplification: use get_quote 'close' or 'ohlc'
             pass

        # Robust way: Get quote
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Some APIs provide 'close' in quote which is prev_close
        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])
        elif not df.empty:
             # Fallback to history
             prev_close = df.iloc[-1]['close']
             # Check if this is today's candle? If so take -2.
             # If timestamp matches today, use -2.
             last_ts = pd.to_datetime(df.iloc[-1]['datetime'] if 'datetime' in df.columns else df.index[-1])
             if last_ts.date() == today.date():
                 if len(df) > 1:
                    prev_close = df.iloc[-2]['close']
             else:
                 prev_close = df.iloc[-1]['close']

        if prev_close == 0:
             logger.error("Could not determine Prev Close")
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

        # Risk Check before order
        if self.rm:
            can_trade, reason = self.rm.can_trade()
            if not can_trade:
                logger.warning(f"Risk blocked trade: {reason}")
                return

        logger.info(f"Executing {option_type} Buy for {qty} qty.")

        # Mock Execution
        # resp = self.client.placesmartorder(...)

        self.pm.update_position(qty, 100, "BUY") # Mock update

        if self.rm:
            # Register Entry (Mock price 100)
            self.rm.register_entry(strike_symbol, qty, 100.0, "LONG")

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
