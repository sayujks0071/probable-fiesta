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

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
from openalgo.strategies.utils.option_analytics import calculate_greeks

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

        # 1. Get Previous Close and Current Price
        # We need NIFTY 50 spot or whatever the underlying is
        search_symbol = self.symbol
        if self.symbol == "NIFTY": search_symbol = "NIFTY 50"
        elif self.symbol == "BANKNIFTY": search_symbol = "NIFTY BANK"

        exchange = "NSE"
        quote = self.client.get_quote(search_symbol, exchange)
        if not quote:
            logger.error(f"Could not fetch quote for {search_symbol}")
            return

        current_price = float(quote['ltp'])
        prev_close = float(quote.get('close', current_price)) # Fallback if close not available

        # If market just opened, 'close' is usually previous close.
        if prev_close == 0:
             # Try history
             logger.info("Quote close is 0, trying history for prev close")
             hist = self.client.history(search_symbol, exchange, interval="day",
                                      start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                                      end_date=datetime.now().strftime("%Y-%m-%d"))
             if not hist.empty:
                  # Last completed candle
                  prev_close = hist.iloc[-2]['close'] if len(hist) > 1 else hist.iloc[-1]['open'] # Approx
             else:
                  logger.error("Could not determine previous close.")
                  return

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Prev Close: {prev_close}, Current: {current_price}, Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        action = "BUY"
        option_type = None

        # Gap UP -> Fade (Expect Down) -> Buy Put
        if gap_pct > self.gap_threshold:
            logger.info("Gap UP detected. Fading (Short Bias). Buying PE.")
            option_type = "PE"
        # Gap DOWN -> Fade (Expect Up) -> Buy Call
        elif gap_pct < -self.gap_threshold:
            logger.info("Gap DOWN detected. Fading (Long Bias). Buying CE.")
            option_type = "CE"

        # 3. Select Option Strike (ATM)
        atm_strike = round(current_price / 50) * 50
        logger.info(f"ATM Strike: {atm_strike}")

        # Find option symbol in chain
        # Need to know expiry.
        # Fetch chain
        opt_exchange = "NFO" if self.symbol != "SENSEX" else "BFO"
        chain = self.client.get_option_chain(self.symbol, opt_exchange)
        if not chain:
             logger.error("Could not fetch option chain.")
             return

        # Filter for ATM strike and correct type
        # Sort by expiry to get nearest
        candidates = [c for c in chain if c['strike'] == atm_strike]
        if not candidates:
             logger.warning(f"No option found for strike {atm_strike}")
             return

        # Sort by expiry date if available, or assume chain returns sorted or nearest
        # APIClient chain structure usually has 'expiry'
        # Assuming sorted by nearest expiry by default from API
        target_option = None

        # We need the specific symbol for the option leg
        # The chain data might have 'ce_symbol', 'pe_symbol' or nested
        # Based on option_analytics.py, it seems flattened or nested.
        # Let's check candidate structure logic
        candidate = candidates[0] # Nearest expiry

        symbol_to_trade = None
        if option_type == "CE":
             symbol_to_trade = candidate.get('ce_symbol') or candidate.get('ce', {}).get('symbol')
        else:
             symbol_to_trade = candidate.get('pe_symbol') or candidate.get('pe', {}).get('symbol')

        if not symbol_to_trade:
             logger.error(f"Could not find symbol for {option_type} at {atm_strike}")
             return

        logger.info(f"Selected Option Symbol: {symbol_to_trade}")

        # 4. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order
        if self.pm.has_position():
             logger.info("Position already exists. Skipping entry.")
             return

        logger.info(f"Placing ORDER: {action} {qty} {symbol_to_trade}")

        resp = self.client.placesmartorder(
            strategy="GapFade",
            symbol=symbol_to_trade,
            action=action,
            exchange=opt_exchange,
            price_type="MARKET",
            product="MIS",
            quantity=qty,
            position_size=qty
        )

        if resp.get('status') == 'success' or 'order_id' in resp:
             logger.info(f"Order Success: {resp}")
             self.pm.update_position(qty, current_price, action) # Using spot price for tracking broadly, ideally fill price
        else:
             logger.error(f"Order Failed: {resp}")

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
