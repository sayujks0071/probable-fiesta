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
    from openalgo.strategies.utils.risk_manager import RiskManager
except ImportError:
    # Fallback for local testing
    sys.path.append(str(project_root / "openalgo"))
    from strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
    from strategies.utils.risk_manager import RiskManager

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
        # Integrate Risk Manager
        self.rm = RiskManager(f"{symbol}_GapFade", exchange="NSE", capital=100000)

    def get_atm_option_symbol(self, underlying, spot_price, option_type):
        """
        Construct ATM option symbol with expiry handling.
        """
        # Try manual construction with rollover logic
        return self._manual_symbol_construction(underlying, spot_price, option_type)

    def _manual_symbol_construction(self, underlying, spot_price, option_type):
        # Improved Manual Construction
        today = datetime.now()

        # Simple heuristic for Monthly Expiry:
        # If today is after the last Thursday of the month (approx > 25th), use next month.
        # This is a simplification. For production, use SymbolResolver or API.

        expiry_date = today
        if today.day > 25:
             # Move to next month (safe jump)
             expiry_date = today + timedelta(days=10)

        month_str = expiry_date.strftime('%b').upper()
        year_str = expiry_date.strftime('%y')

        # Round to nearest 50 for NIFTY
        strike = round(spot_price / 50) * 50

        # Symbol Format: NIFTY23OCT19500CE
        return f"{underlying}{year_str}{month_str}{strike}{option_type}"

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Check Failed: {reason}")
            return

        # 1. Get Previous Close
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        if df.empty or len(df) < 1:
            logger.error("Could not fetch history for previous close.")
            return

        prev_close = df.iloc[-1]['close']

        # Try to get real-time quote for more accuracy
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        trade_action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            logger.info("Gap UP detected. Looking to FADE (Short).")
            option_type = "PE"
            trade_action = "BUY"

        elif gap_pct < -self.gap_threshold:
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            option_type = "CE"
            trade_action = "BUY"

        # 3. Select Option Strike (ATM)
        strike_symbol = self.get_atm_option_symbol(self.symbol, current_price, option_type)

        logger.info(f"Signal: Buy {option_type} - {strike_symbol} (Gap Fade)")

        # 4. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote and 'ltp' in vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order via API
        resp = self.client.placesmartorder("GapFade", strike_symbol, trade_action, "NFO", "MARKET", "MIS", qty, qty)

        if resp and resp.get('status') == 'success':
            logger.info(f"Executed {option_type} Buy for {qty} qty.")

            # Register with Risk Manager
            opt_quote = self.client.get_quote(strike_symbol, "NFO")
            entry_price = float(opt_quote['ltp']) if opt_quote and 'ltp' in opt_quote else 100.0

            # Set initial Stop Loss at 20%
            sl = entry_price * 0.8
            self.rm.register_entry(strike_symbol, qty, entry_price, "LONG", stop_loss=sl)
        else:
            logger.error(f"Order Execution Failed: {resp}")

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
