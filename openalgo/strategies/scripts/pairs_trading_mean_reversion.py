#!/usr/bin/env python3
"""
Pairs Trading Mean Reversion Strategy
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
    # Fallback/Mock
    class APIClient:
        def __init__(self, api_key, host): pass
        def placesmartorder(self, **kwargs): return {}
    class PositionManager:
        def __init__(self, symbol): pass
    def is_market_open(exchange="NSE"): return True
    def is_mcx_market_open(): return True

class PairsTradingStrategy:
    def __init__(self, symbol_x, symbol_y, api_key, port=5001):
        self.symbol_x = symbol_x
        self.symbol_y = symbol_y
        self.client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{port}")
        self.logger = logging.getLogger(f"PairsTrading_{symbol_x}_{symbol_y}")
        logging.basicConfig(level=logging.INFO)

        # Determine exchange from symbols (Checking X is usually sufficient if they are same exchange)
        self.exchange = "MCX" if "FUT" in symbol_x else "NSE"
        self.logger.info(f"Initialized Pairs Strategy for {self.symbol_x}/{self.symbol_y} on {self.exchange}")

    def execute_trade(self, symbol, action, quantity):
        """Execute trade - NOTE: strategy is REQUIRED first argument!"""
        try:
            order = self.client.placesmartorder(
                strategy="PairsTrading",     # REQUIRED!
                symbol=symbol,
                action=action,
                exchange=self.exchange,
                price_type="MARKET",
                product="MIS",
                quantity=quantity,
                position_size=quantity
            )
            self.logger.info(f"ORDER {action} {quantity} {symbol}: {order}")
            return order
        except Exception as e:
            self.logger.error(f"Trade failed for {symbol}: {e}")
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
            self.logger.info(f"Checking spread between {self.symbol_x} and {self.symbol_y}...")

            # Example logic (placeholder)
            # spread = price_x - price_y
            # if spread > threshold:
            #     self.execute_trade(self.symbol_x, "SELL", 1)
            #     self.execute_trade(self.symbol_y, "BUY", 1)

            time.sleep(30)

if __name__ == "__main__":
    symbol_x = os.getenv('SYMBOL_X')
    symbol_y = os.getenv('SYMBOL_Y')
    api_key = os.getenv('OPENALGO_APIKEY')

    if not symbol_x or not symbol_y:
        print("ERROR: Set SYMBOL_X and SYMBOL_Y env variables!")
        print("Example: SYMBOL_X=GOLDM05FEB26FUT SYMBOL_Y=SILVERM27FEB26FUT")
        sys.exit(1)

    strategy = PairsTradingStrategy(symbol_x=symbol_x, symbol_y=symbol_y, api_key=api_key)
    strategy.run()
