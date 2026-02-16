#!/usr/bin/env python3
"""
Gap Fade Strategy (Fixed)

Strategies:
- Fades the opening gap if it exceeds a threshold.
- Uses RiskManager for position sizing and safety.
- correctly resolves Option symbols (ATM/ITM/OTM).
- Checks market hours.
"""

import sys
import os
import argparse
import logging
import time
import pandas as pd
from datetime import datetime, timedelta

# Ensure project root is in path
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
    from openalgo.strategies.utils.risk_manager import RiskManager
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    from openalgo_observability.logging_setup import setup_logging
except ImportError:
    # Fallback
    sys.path.append(os.path.join(project_root, 'openalgo'))
    from strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
    from strategies.utils.risk_manager import RiskManager
    from strategies.utils.symbol_resolver import SymbolResolver
    def setup_logging():
        logging.basicConfig(level=logging.INFO)

setup_logging()
logger = logging.getLogger("GapFadeStrategy")

class GapFadeStrategy:
    def __init__(self, symbol="NIFTY", qty=50, gap_threshold=0.5, api_key=None, host=None, client=None):
        self.symbol = normalize_symbol(symbol)
        self.qty = qty
        self.gap_threshold = gap_threshold
        self.trade_symbol = None

        if client:
            self.client = client
        else:
            self.api_key = api_key or os.getenv("OPENALGO_API_KEY")
            self.host = host or os.getenv("OPENALGO_HOST", "http://127.0.0.1:5001")
            if not self.api_key:
                raise ValueError("API Key required")
            self.client = APIClient(api_key=self.api_key, host=self.host)

        self.rm = RiskManager(f"{self.symbol}_GapFade", exchange="NSE")
        self.pm = PositionManager(f"{self.symbol}_GapFade")
        self.resolver = SymbolResolver()
        self.executed_today = False

        # Recover state
        self._recover_state()

    def _recover_state(self):
        """Recover active position state from RiskManager."""
        open_positions = self.rm.get_open_positions()
        if open_positions:
            # Assuming this strategy manages one position at a time
            # We take the first one found that looks like an option for this symbol (or just the first one)
            self.trade_symbol = list(open_positions.keys())[0]
            self.executed_today = True
            logger.info(f"Recovered active trade symbol: {self.trade_symbol}")

    def get_previous_close(self):
        """Get previous day's close."""
        try:
            # Try to get from Quote first (often has 'close' or 'ohlc')
            quote = self.client.get_quote(self.symbol, "NSE_INDEX" if "NIFTY" in self.symbol else "NSE")
            if quote and 'close' in quote and quote['close'] > 0:
                return float(quote['close'])

            # Fallback to history
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            df = self.client.history(self.symbol, interval="day", start_date=start_date, end_date=end_date)

            if not df.empty and len(df) >= 1:
                # If last row is today (check date), use prev row
                last_date = pd.to_datetime(df.iloc[-1]['date']).date()
                if last_date == datetime.now().date():
                    if len(df) >= 2:
                        return df.iloc[-2]['close']
                else:
                    return df.iloc[-1]['close']
            return None
        except Exception as e:
            logger.error(f"Error fetching prev close: {e}")
            return None

    def execute(self):
        logger.info(f"Starting Gap Fade Strategy for {self.symbol}")

        while True:
            try:
                # 1. Check Market Hours
                if not is_market_open("NSE"):
                    logger.info("Market Closed. Sleeping...")
                    time.sleep(60)
                    continue

                # 2. Risk Checks
                can_trade, reason = self.rm.can_trade()
                if not can_trade:
                    # Allow closing existing positions even if new trades are blocked?
                    # RiskManager usually blocks new entries.
                    if not self.pm.has_position():
                        logger.warning(f"Risk Block: {reason}")
                        time.sleep(60)
                        continue

                # 3. Monitor Active Position (or check if already traded)
                if self.pm.has_position() or self.executed_today:
                    if self.trade_symbol and self.pm.has_position():
                        quote = self.client.get_quote(self.trade_symbol, "NFO")
                        if quote:
                            ltp = float(quote['ltp'])
                            stop_hit, reason = self.rm.check_stop_loss(self.trade_symbol, ltp)
                            if stop_hit:
                                logger.info(f"Exit: {reason}")
                                self.close_position(ltp, reason)
                            else:
                                self.rm.update_trailing_stop(self.trade_symbol, ltp)

                    # EOD Check
                    if self.rm.should_square_off_eod():
                         if self.pm.has_position():
                             self.close_position(0, "EOD") # Market order

                    time.sleep(10)
                    continue

                # 4. Gap Logic (Only run near Open, e.g., 9:15-9:30)
                now = datetime.now().time()
                if now.hour == 9 and now.minute < 30:
                    prev_close = self.get_previous_close()
                    if not prev_close:
                        time.sleep(10)
                        continue

                    quote = self.client.get_quote(self.symbol, "NSE_INDEX" if "NIFTY" in self.symbol else "NSE")
                    if not quote:
                        continue

                    current_price = float(quote['ltp'])
                    gap_pct = ((current_price - prev_close) / prev_close) * 100

                    logger.info(f"Gap: {gap_pct:.2f}% (Thresh: {self.gap_threshold}%)")

                    if abs(gap_pct) > self.gap_threshold:
                        # Signal!
                        option_type = "PE" if gap_pct > 0 else "CE" # Fade: Gap Up -> Buy PE
                        action = "BUY"

                        # Resolve Option Symbol
                        opt_config = {
                            'type': 'OPT',
                            'underlying': self.symbol,
                            'option_type': option_type,
                            'expiry_preference': 'WEEKLY',
                            'strike_criteria': 'ATM',
                            'exchange': 'NFO'
                        }
                        self.trade_symbol = self.resolver.get_tradable_symbol(opt_config, spot_price=current_price)

                        if not self.trade_symbol:
                            logger.error("Could not resolve option symbol")
                            continue

                        logger.info(f"Signal: Buy {self.trade_symbol} (Gap Fade)")

                        # Calculate Quantity based on VIX?
                        vix = self.client.get_vix() or 15
                        qty = self.qty
                        if vix > 25: qty = max(1, int(qty * 0.5))

                        # Place Order
                        resp = self.client.placesmartorder(
                            strategy="GapFade",
                            symbol=self.trade_symbol,
                            action="BUY",
                            exchange="NFO",
                            price_type="MARKET",
                            product="MIS",
                            quantity=qty,
                            position_size=qty
                        )

                        if resp and resp.get('status') == 'success':
                            # Get fill price (approx LTP)
                            quote = self.client.get_quote(self.trade_symbol, "NFO")
                            fill_price = float(quote['ltp']) if quote else current_price # Fallback?

                            self.pm.update_position(qty, fill_price, "BUY")

                            # Register with Risk Manager (Stop Loss 10% of Premium?)
                            stop_price = fill_price * 0.9
                            self.rm.register_entry(self.trade_symbol, qty, fill_price, "BUY", stop_loss=stop_price)
                            self.executed_today = True

                time.sleep(10)

            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(10)

    def close_position(self, price, reason):
        action = "SELL"
        qty = abs(self.pm.position)
        self.client.placesmartorder(
            strategy="GapFade",
            symbol=self.trade_symbol,
            action=action,
            exchange="NFO",
            price_type="MARKET",
            product="MIS",
            quantity=qty,
            position_size=qty
        )
        self.pm.update_position(qty, price, action)
        self.rm.register_exit(self.trade_symbol, price, qty)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--api_key", help="API Key")
    parser.add_argument("--host", help="API Host")
    args = parser.parse_args()

    try:
        strategy = GapFadeStrategy(args.symbol, args.qty, args.threshold, args.api_key, args.host)
        strategy.execute()
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")

if __name__ == "__main__":
    main()
