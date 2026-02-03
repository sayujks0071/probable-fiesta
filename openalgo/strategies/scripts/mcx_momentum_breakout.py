#!/usr/bin/env python3
"""
MCX Momentum Breakout Strategy
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta

# Add paths
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open, is_mcx_market_open
except ImportError:
    # Fallback/Mock for testing if utils not found
    class APIClient:
        def __init__(self, api_key, host): pass
        def placesmartorder(self, **kwargs): return {}
    class PositionManager:
        def __init__(self, symbol): pass
    def is_market_open(exchange="NSE"): return True
    def is_mcx_market_open(): return True

class MCXMomentumBreakout:
    def __init__(self, symbol, api_key, port=5001):
        self.symbol = symbol
        self.client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{port}")
        self.logger = logging.getLogger(f"MCXMomentumBreakout_{symbol}")
        logging.basicConfig(level=logging.INFO)

        # Determine exchange from symbol
        self.exchange = "MCX" if "FUT" in symbol else "NSE"
        self.logger.info(f"Initialized strategy for {self.symbol} on {self.exchange}")

    def execute_trade(self, action, quantity):
        """Execute trade - NOTE: strategy is REQUIRED first argument!"""
        try:
            order = self.client.placesmartorder(
                strategy="MCXMomentumBreakout",     # REQUIRED!
                symbol=self.symbol,
                action=action,
                exchange=self.exchange,
                price_type="MARKET",
                product="MIS",
                quantity=quantity,
                position_size=quantity
            )
            self.logger.info(f"ORDER {action} {quantity}: {order}")
            return order
        except Exception as e:
            self.logger.error(f"Trade failed: {e}")
            return None

    def run(self):
        self.logger.info("Starting strategy loop...")
        while True:
            # Use correct market hours check!
            if self.exchange == "MCX":
                if not is_mcx_market_open():
                    self.logger.info("MCX market closed")
                    time.sleep(60)
                    continue
            else:
                if not is_market_open(exchange=self.exchange):
                    self.logger.info("NSE market closed")
                    time.sleep(60)
                    continue

            # Strategy logic here...
            # For demonstration, we just log "Processing"
            self.logger.info(f"Processing {self.symbol}...")

            # Example trade logic (placeholder)
            # if condition:
            #     self.execute_trade("BUY", 1)

            time.sleep(30)

if __name__ == "__main__":
    symbol = os.getenv('SYMBOL')  # e.g., CRUDEOIL19FEB26FUT
    api_key = os.getenv('OPENALGO_APIKEY')

    if not symbol:
        print("ERROR: Set SYMBOL env variable with full expiry format!")
        print("Example: SYMBOL=CRUDEOIL19FEB26FUT")
        sys.exit(1)

    strategy = MCXMomentumBreakout(symbol=symbol, api_key=api_key)
    strategy.run()
