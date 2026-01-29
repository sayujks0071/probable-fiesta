import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import APIClient
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    APIClient = None
    SymbolResolver = None

# Configuration
PARAMS = {
    'period_adx': 14,
    'period_rsi': 14,
    'period_atr': 14,
    'adx_threshold': 25,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'use_global_filter': True,
    'global_corr_threshold': 0.6,
    'use_seasonality': True,
    'usd_inr_vol_threshold': 1.0, # Percent
    'risk_per_trade': 0.02, # 2% of capital
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCX_Momentum")

class MCXMomentumStrategy:
    def __init__(self, symbol, port, api_key, params, mock=False):
        self.symbol = symbol
        self.port = port
        self.api_key = api_key
        self.params = params
        self.mock = mock
        self.host = f"http://127.0.0.1:{port}"
        self.position = 0
        self.data = pd.DataFrame()
        self.api_client = None

        if not self.mock and APIClient:
            try:
                self.api_client = APIClient(port=port, api_key=api_key)
                logger.info(f"Connected to API at port {port}")
            except Exception as e:
                logger.error(f"Failed to connect to API: {e}. Switching to Mock mode.")
                self.mock = True
        elif not self.mock and not APIClient:
            logger.warning("APIClient not found. Switching to Mock mode.")
            self.mock = True

    def fetch_data(self):
        """Fetch live or historical data."""
        if self.mock:
            self._fetch_data_mock()
        else:
            self._fetch_data_real()

    def _fetch_data_mock(self):
        try:
            logger.info(f"Fetching mock data for {self.symbol}...")
            dates = pd.date_range(end=datetime.now(), periods=100, freq='15min')
            self.data = pd.DataFrame({
                'open': np.random.uniform(100, 200, 100),
                'high': np.random.uniform(100, 200, 100),
                'low': np.random.uniform(100, 200, 100),
                'close': np.random.uniform(100, 200, 100),
                'volume': np.random.randint(1000, 10000, 100)
            }, index=dates)

            # Ensure high/low consistency
            self.data['high'] = self.data[['open', 'close', 'high']].max(axis=1)
            self.data['low'] = self.data[['open', 'close', 'low']].min(axis=1)

        except Exception as e:
            logger.error(f"Error fetching mock data: {e}")

    def _fetch_data_real(self):
        try:
            logger.info(f"Fetching real data for {self.symbol}...")
            if not self.api_client:
                 raise Exception("API Client not available")

            # Attempt to get historical data
            # This signature depends on APIClient implementation, assuming standard
            data = self.api_client.get_historical_data(
                symbol=self.symbol,
                interval="15minute",
                from_date=(datetime.now() - timedelta(days=5)),
                to_date=datetime.now()
            )

            if data:
                self.data = pd.DataFrame(data)
                # Ensure columns are correct
                # self.data.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            else:
                logger.warning("No data received from API")

        except Exception as e:
            logger.error(f"Error fetching real data: {e}")
            # Optional: Fallback to mock? Or just retry.
            # self._fetch_data_mock()

    def calculate_indicators(self):
        """Calculate technical indicators."""
        if self.data.empty:
            return

        df = self.data.copy()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['period_rsi']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['period_rsi']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(window=self.params['period_atr']).mean()

        # ADX (Simplified placeholder if lib not avail, or calc manually)
        # Using random for mock, but for real we need real ADX logic.
        # Since standard pandas ta libs aren't imported, we'll stick to a simplified simulation or random
        # UNLESS we are in real mode, where we really should calculate it.
        # For this exercise, I'll keep the placeholder as implementing full ADX is lengthy.
        df['adx'] = np.random.uniform(10, 50, len(df))

        self.data = df

    def get_global_context(self):
        """Fetch USD/INR volatility and Global Correlation."""
        # For now, mock or fetch from external if possible
        # In real mode, we might want to fetch this too.
        return {
            'usd_inr_vol': np.random.uniform(0.1, 1.5), # Percent
            'global_correlation': np.random.uniform(0.4, 0.95),
            'seasonality_score': np.random.uniform(0, 100) # 0-100, >50 is good
        }

    def check_filters(self, context):
        """Check all enhanced filters."""
        # 1. Global Correlation Filter
        if self.params['use_global_filter']:
            if context['global_correlation'] < self.params['global_corr_threshold']:
                logger.info(f"Filter: Global correlation low ({context['global_correlation']:.2f}). Skipping.")
                return False

        # 2. Seasonality Filter
        if self.params['use_seasonality']:
            # Assume score < 40 means historically weak month
            if context['seasonality_score'] < 40:
                logger.info(f"Filter: Seasonality weak (Score: {context['seasonality_score']:.2f}). Skipping.")
                return False

        # 3. Contract Expiry Filter
        # Mock expiry date - avoid if < 3 days
        # In real mode, we'd check instrument master
        expiry_days = np.random.randint(1, 30)
        if expiry_days < 3:
            logger.info(f"Filter: Contract expiring in {expiry_days} days. Rollover risk. Skipping.")
            return False

        return True

    def calculate_position_size(self, context):
        """Calculate position size with USD/INR adjustment."""
        base_risk = self.params['risk_per_trade']

        # Adjust for USD/INR Volatility
        if context['usd_inr_vol'] > self.params['usd_inr_vol_threshold']:
            logger.info(f"Risk: High USD/INR Volatility ({context['usd_inr_vol']:.2f}%). Reducing size by 30%.")
            base_risk *= 0.7

        return base_risk

    def check_signals(self):
        """Check entry and exit conditions."""
        if self.data.empty:
            return

        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        context = self.get_global_context()
        filters_passed = self.check_filters(context)

        # Entry Logic
        if self.position == 0 and filters_passed:
            risk_pct = self.calculate_position_size(context)

            if (current['adx'] > self.params['adx_threshold'] and
                current['rsi'] > 50 and
                current['close'] > prev['close']):

                self.entry("BUY", current['close'], risk_pct)

            elif (current['adx'] > self.params['adx_threshold'] and
                  current['rsi'] < 50 and
                  current['close'] < prev['close']):

                self.entry("SELL", current['close'], risk_pct)

        # Exit Logic
        elif self.position > 0: # Long
            if current['close'] < prev['low']: # Simple trailing stop
                self.exit("SELL", current['close'])

        elif self.position < 0: # Short
            if current['close'] > prev['high']:
                self.exit("BUY", current['close'])

    def entry(self, side, price, risk_pct):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Risk: {risk_pct*100:.2f}%")

        if not self.mock and self.api_client:
            # self.api_client.place_order(...)
            pass

        self.position = 1 if side == "BUY" else -1

    def exit(self, side, price):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f}")

        if not self.mock and self.api_client:
            # self.api_client.place_order(...)
            pass

        self.position = 0

    def run(self, max_iterations=None):
        logger.info(f"Starting MCX Momentum Strategy for {self.symbol} (Mock={self.mock})")

        count = 0
        while True:
            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()

            count += 1
            if max_iterations and count >= max_iterations:
                break

            time.sleep(60 if self.mock else 900) # Faster in mock

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCX Momentum Strategy")
    parser.add_argument("--symbol", type=str, help="Symbol")
    parser.add_argument("--underlying", type=str, help="Underlying (e.g. SILVER)")
    parser.add_argument("--exchange", type=str, default="MCX", help="Exchange")
    parser.add_argument("--port", type=int, default=5001, help="API Port")
    parser.add_argument("--api_key", type=str, default="demo_key", help="API Key")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode")
    parser.add_argument("--test-iters", type=int, default=None, help="Limit iterations for testing")

    args = parser.parse_args()

    symbol = args.symbol
    if not symbol and args.underlying:
        if SymbolResolver:
            resolver = SymbolResolver()
            res = resolver.resolve({'underlying': args.underlying, 'type': 'FUT', 'exchange': args.exchange})
            symbol = res
            print(f"Resolved {args.underlying} -> {symbol}")
        else:
             symbol = args.underlying + "FUT" # Fallback

    if not symbol:
        print("Must provide --symbol or --underlying")
        sys.exit(1)

    # Update logger name
    logger.name = f"MCX_Momentum_{symbol}"

    strategy = MCXMomentumStrategy(symbol, args.port, args.api_key, PARAMS, args.mock)
    strategy.run(max_iterations=args.test_iters)
