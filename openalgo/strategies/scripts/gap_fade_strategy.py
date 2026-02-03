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

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, SmartOrder
from openalgo.strategies.utils.risk_manager import RiskManager
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

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
        self.rm = RiskManager(f"{symbol}_GapFade", "NSE", capital=100000)
        self.resolver = SymbolResolver()
        self.smart_order = SmartOrder(self.client)

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Manager Block: {reason}")
            return

        # 1. Get Previous Close
        # Using history API for last 5 days
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        # Note: 'symbol' here is typically NIFTY (Index), but history usually needs 'NIFTY 50' or similar
        # Depending on backend, 'NIFTY' might work if mapped. Using "NIFTY 50" as safe default for indices if symbol is NIFTY
        history_symbol = f"{self.symbol} 50" if self.symbol == "NIFTY" else self.symbol

        df = self.client.history(history_symbol, interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0.0
        if not df.empty and len(df) >= 1:
             prev_close = df.iloc[-1]['close']

        # Try to get better prev_close from quote
        quote = self.client.get_quote(history_symbol, "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Some APIs provide 'close' in quote which is prev_close
        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])

        if prev_close == 0:
             logger.error("Could not determine Previous Close")
             return

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Buy PE).")
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Buy CE).")
            option_type = "CE"

        # 3. Select Option Symbol via Resolver
        opt_config = {
            'type': 'OPT',
            'underlying': self.symbol,
            'option_type': option_type,
            'exchange': 'NFO',
            'strike_criteria': 'ATM',
            'expiry_preference': 'WEEKLY'
        }

        tradable_symbol = self.resolver.get_tradable_symbol(opt_config, spot_price=current_price)

        if not tradable_symbol:
            logger.error(f"Could not resolve option symbol for {self.symbol} {option_type}")
            return

        logger.info(f"Signal: Buy {tradable_symbol} (Gap Fade)")

        # 4. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order
        if self.pm.has_position():
             logger.info("Position already exists (managed by PositionManager). Skipping.")
             return

        # Execute
        resp = self.smart_order.place_adaptive_order(
            strategy="GapFade",
            symbol=tradable_symbol,
            action="BUY",
            exchange="NFO",
            quantity=qty,
            urgency="MEDIUM"
        )

        if resp and resp.get('status') == 'success':
            # Attempt to estimate entry price
            avg_price = 0.0
            if 'average_price' in resp:
                avg_price = float(resp['average_price'])

            if avg_price == 0:
                 # Fallback check
                 q_opt = self.client.get_quote(tradable_symbol, "NFO")
                 avg_price = float(q_opt['ltp']) if q_opt else 0

            # Register with Risk Manager and Position Manager
            self.rm.register_entry(tradable_symbol, qty, avg_price, "LONG")
            self.pm.update_position(qty, avg_price, "BUY")
            logger.info(f"Trade Executed: {tradable_symbol} @ {avg_price}")
        else:
            logger.error(f"Order Placement Failed: {resp}")

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
