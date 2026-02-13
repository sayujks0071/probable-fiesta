#!/usr/bin/env python3
"""
Pairs Trading Mean Reversion Strategy
Statistical Arbitrage on MCX Pairs (Gold/Silver) using Z-scores.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_mcx_market_open
    from symbol_resolver import SymbolResolver
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_mcx_market_open
        from utils.symbol_resolver import SymbolResolver
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_mcx_market_open
            from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            sys.exit(1)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PairsTradingMeanReversion")

class PairsTradingMeanReversion:
    def __init__(self, symbol_a, symbol_b, api_key, host, z_entry=2.0, z_exit=0.5):
        self.symbol_a = symbol_a
        self.symbol_b = symbol_b
        self.api_key = api_key
        self.host = host
        self.z_entry = z_entry
        self.z_exit = z_exit

        self.client = APIClient(api_key=self.api_key, host=self.host)
        self.pm_a = PositionManager(symbol_a)
        self.pm_b = PositionManager(symbol_b)
        self.data = pd.DataFrame()

        logger.info(f"Initialized Pairs Strategy for {symbol_a} vs {symbol_b}")
        logger.info(f"Z-Score Thresholds: Entry={z_entry}, Exit={z_exit}")

    def fetch_data(self):
        """Fetch live or historical data for both symbols."""
        try:
            # Fetch last 5 days
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

            logger.info(f"Fetching data for {self.symbol_a}...")
            df_a = self.client.history(
                symbol=self.symbol_a,
                interval="15m",
                exchange="MCX",
                start_date=start_date,
                end_date=end_date
            )

            logger.info(f"Fetching data for {self.symbol_b}...")
            df_b = self.client.history(
                symbol=self.symbol_b,
                interval="15m",
                exchange="MCX",
                start_date=start_date,
                end_date=end_date
            )

            if not df_a.empty and not df_b.empty:
                # Merge on datetime
                df = pd.merge(df_a[['datetime', 'close']], df_b[['datetime', 'close']], on='datetime', suffixes=('_a', '_b'))
                df = df.sort_values('datetime')
                self.data = df
                logger.info(f"Merged Data: {len(df)} rows.")
            else:
                logger.warning(f"Insufficient data for {self.symbol_a} or {self.symbol_b}.")

        except Exception as e:
            logger.error(f"Error fetching data: {e}", exc_info=True)

    def calculate_z_score(self):
        """Calculate Z-Score of the Price Ratio."""
        if self.data.empty:
            return

        df = self.data.copy()

        # Calculate Ratio
        df['ratio'] = df['close_a'] / df['close_b']

        # Calculate Rolling Stats (20 period)
        window = 20
        df['mean'] = df['ratio'].rolling(window=window).mean()
        df['std'] = df['ratio'].rolling(window=window).std()

        # Calculate Z-Score
        df['z_score'] = (df['ratio'] - df['mean']) / df['std']

        self.data = df

    def check_signals(self):
        """Check entry and exit conditions based on Z-Score."""
        if self.data.empty or 'z_score' not in self.data.columns:
            return

        current = self.data.iloc[-1]
        z_score = current['z_score']

        if pd.isna(z_score):
            return

        logger.info(f"Current Z-Score: {z_score:.4f} | Ratio: {current['ratio']:.4f}")

        # Positions
        pos_a = self.pm_a.position
        pos_b = self.pm_b.position

        has_position = (pos_a != 0) or (pos_b != 0)

        # Entry Logic
        if not has_position:
            # Short the Ratio (Sell A, Buy B) if Z > Entry Threshold
            if z_score > self.z_entry:
                logger.info(f"ENTRY SIGNAL: Short Ratio (Z={z_score:.2f} > {self.z_entry})")
                self.execute_trade(self.symbol_a, 'SELL')
                self.execute_trade(self.symbol_b, 'BUY')

            # Long the Ratio (Buy A, Sell B) if Z < -Entry Threshold
            elif z_score < -self.z_entry:
                logger.info(f"ENTRY SIGNAL: Long Ratio (Z={z_score:.2f} < -{self.z_entry})")
                self.execute_trade(self.symbol_a, 'BUY')
                self.execute_trade(self.symbol_b, 'SELL')

        # Exit Logic
        elif has_position:
            # Exit if Z-score reverts to within Exit Threshold
            if abs(z_score) < self.z_exit:
                logger.info(f"EXIT SIGNAL: Mean Reversion (Z={z_score:.2f} < {self.z_exit})")
                self.close_positions()

            # Optional Stop Loss or Max Z-score can be added here

    def execute_trade(self, symbol, action):
        """Execute trade using placesmartorder."""
        try:
            # Exchange Detection
            exchange = "MCX" if "FUT" in symbol else "NSE"

            # Place Order
            response = self.client.placesmartorder(
                strategy="Pairs Trading Mean Reversion",
                symbol=symbol,
                action=action,
                exchange=exchange,
                price_type="MARKET",
                product="MIS",
                quantity=1, # MCX Quantity is 1 lot
                position_size=1
            )

            logger.info(f"Order Placed for {symbol} {action}: {response}")

            # Update Position Manager (assuming fill for now, or based on response)
            # In live, we might wait for confirmation, but here we update state optimistically or check
            if response and response.get('status') == 'success':
                 # Using current price for PnL tracking in PM (approx)
                 current_price = self.data.iloc[-1]['close_a'] if symbol == self.symbol_a else self.data.iloc[-1]['close_b']
                 qty = 1
                 if action == 'SELL':
                     self.pm_a.update_position(qty, current_price, 'SELL') if symbol == self.symbol_a else self.pm_b.update_position(qty, current_price, 'SELL')
                 else:
                     self.pm_a.update_position(qty, current_price, 'BUY') if symbol == self.symbol_a else self.pm_b.update_position(qty, current_price, 'BUY')

        except Exception as e:
            logger.error(f"Failed to execute trade for {symbol}: {e}")

    def close_positions(self):
        """Close all open positions."""
        # Close A
        if self.pm_a.position != 0:
            action = 'SELL' if self.pm_a.position > 0 else 'BUY'
            self.execute_trade(self.symbol_a, action)

        # Close B
        if self.pm_b.position != 0:
            action = 'SELL' if self.pm_b.position > 0 else 'BUY'
            self.execute_trade(self.symbol_b, action)

    def run(self):
        logger.info("Starting Strategy Loop...")
        while True:
            # Market Hours Check
            if not is_mcx_market_open():
                logger.info("MCX Market is Closed. Sleeping...")
                time.sleep(300)
                continue

            self.fetch_data()
            self.calculate_z_score()
            self.check_signals()

            time.sleep(60) # Check every minute

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pairs Trading Mean Reversion Strategy')
    parser.add_argument('--symbol_a', type=str, help='First Symbol (e.g., GOLDM...)')
    parser.add_argument('--symbol_b', type=str, help='Second Symbol (e.g., SILVERM...)')
    parser.add_argument('--z_entry', type=float, default=2.0, help='Z-Score Entry Threshold (Default: 2.0)')
    parser.add_argument('--z_exit', type=float, default=0.5, help='Z-Score Exit Threshold (Default: 0.5)')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    # Resolve Symbols if not provided
    symbol_a = args.symbol_a
    symbol_b = args.symbol_b

    if not symbol_a or not symbol_b:
        logger.info("Resolving Default MCX Pairs (Gold/Silver)...")
        if SymbolResolver:
            resolver = SymbolResolver()
            if not symbol_a:
                symbol_a = resolver.resolve({'underlying': 'GOLD', 'type': 'FUT', 'exchange': 'MCX'})
            if not symbol_b:
                symbol_b = resolver.resolve({'underlying': 'SILVER', 'type': 'FUT', 'exchange': 'MCX'})

    if not symbol_a or not symbol_b:
        logger.error("Could not resolve symbols. Please provide --symbol_a and --symbol_b")
        sys.exit(1)

    logger.info(f"Trading Pair: {symbol_a} vs {symbol_b}")

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
    port = args.port or int(os.getenv('OPENALGO_PORT', 5001))
    host = f"http://127.0.0.1:{port}"

    strategy = PairsTradingMeanReversion(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        api_key=api_key,
        host=host,
        z_entry=args.z_entry,
        z_exit=args.z_exit
    )
    strategy.run()
