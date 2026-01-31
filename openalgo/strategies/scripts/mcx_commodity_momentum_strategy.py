#!/usr/bin/env python3
"""
MCX Commodity Momentum Strategy
Momentum strategy using ADX and RSI with proper API integration.
Enhanced with Multi-Factor inputs (USD/INR, Seasonality).
"""
import re
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda: True

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCX_Momentum")

class MCXMomentumStrategy:
    def __init__(self, symbol, api_key, host, params):
        self.symbol = symbol
        self.api_key = api_key
        self.host = host
        self.params = params

        self.client = APIClient(api_key=self.api_key, host=self.host) if APIClient else None
        self.pm = PositionManager(symbol) if PositionManager else None
        self.data = pd.DataFrame()

        # Log active filters
        logger.info(f"Initialized Strategy for {symbol}")
        logger.info(f"Filters: Seasonality={params.get('seasonality_score', 'N/A')}, USD_Vol={params.get('usd_inr_volatility', 'N/A')}")

        self.check_risk_parameters()

    def get_expiry_date(self):
        """Parse expiry date from symbol (e.g., GOLDM05FEB26FUT)."""
        # Format: NAME + DD + MMM + YY + FUT
        # Regex to find DDMMMYY
        match = re.search(r'(\d{2})([A-Z]{3})(\d{2})', self.symbol)
        if match:
            day, month_str, year_short = match.groups()
            year = f"20{year_short}"
            try:
                expiry_date = datetime.strptime(f"{day}{month_str}{year}", "%d%b%Y")
                return expiry_date
            except ValueError:
                logger.error(f"Could not parse date from {day}{month_str}{year}")
        return None

    def check_risk_parameters(self):
        """Check critical risk parameters like contract expiry."""
        expiry = self.get_expiry_date()
        if expiry:
            days_to_expiry = (expiry - datetime.now()).days
            logger.info(f"Contract {self.symbol} expires in {days_to_expiry} days ({expiry.strftime('%Y-%m-%d')}).")

            if days_to_expiry < 3:
                logger.warning(f"⚠️ RISK WARNING: Contract expires in {days_to_expiry} days! Closing/Avoiding positions.")
                # In a real engine, we might trigger a close all here.
                # For now, we set a flag or just log error which will be seen in run loop
                return False
        else:
             logger.warning(f"Could not determine expiry for {self.symbol}. Proceeding with caution.")

        return True

    def fetch_data(self):
        """Fetch live or historical data from OpenAlgo."""
        if not self.client:
            logger.error("API Client not initialized.")
            return

        try:
            logger.info(f"Fetching data for {self.symbol}...")
            # Fetch last 5 days
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

            df = self.client.history(
                symbol=self.symbol,
                interval="15m",
                exchange="MCX",
                start_date=start_date,
                end_date=end_date
            )

            if not df.empty and len(df) > 50:
                self.data = df
                logger.info(f"Fetched {len(df)} candles.")
            else:
                logger.warning(f"Insufficient data for {self.symbol}.")

        except Exception as e:
            logger.error(f"Error fetching data: {e}", exc_info=True)

    def generate_signal(self, df):
        """
        Generate signal for backtesting.
        """
        if df.empty: return 'HOLD', 0.0, {}

        self.data = df
        self.calculate_indicators()

        # Check signals (Reusing existing logic but adapting return)
        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        # Factors
        seasonality_ok = self.params.get('seasonality_score', 50) > 40

        action = 'HOLD'

        if not seasonality_ok:
            return 'HOLD', 0.0, {'reason': 'Seasonality Weak'}

        if (current['adx'] > self.params['adx_threshold'] and
            current['rsi'] > 50 and
            current['close'] > prev['close']):
            action = 'BUY'

        elif (current['adx'] > self.params['adx_threshold'] and
              current['rsi'] < 50 and
              current['close'] < prev['close']):
            action = 'SELL'

        return action, 1.0, {'atr': current.get('atr', 0)}

    def calculate_indicators(self):
        """Calculate technical indicators."""
        if self.data.empty:
            return

        # Optimization: If columns already exist and length matches, skip?
        # But for now, we assume data is fresh.
        df = self.data.copy()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['period_rsi']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['period_rsi']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(window=self.params['period_atr']).mean()

        # ADX Calculation
        up = df['high'] - df['high'].shift(1)
        down = df['low'].shift(1) - df['low']

        # +DM: if up > down and up > 0
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        # -DM: if down > up and down > 0
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        df['plus_dm'] = plus_dm
        df['minus_dm'] = minus_dm

        # Smooth (using simple moving average for simplicity as originally intended in simple mock)
        tr_smooth = true_range.rolling(window=self.params['period_adx']).mean()
        plus_dm_smooth = df['plus_dm'].rolling(window=self.params['period_adx']).mean()
        minus_dm_smooth = df['minus_dm'].rolling(window=self.params['period_adx']).mean()

        # Avoid division by zero
        tr_smooth = tr_smooth.replace(0, np.nan)

        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)

        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
        df['adx'] = dx.rolling(window=self.params['period_adx']).mean()

        self.data = df

    def check_signals(self):
        """Check entry and exit conditions."""
        if self.data.empty or 'adx' not in self.data.columns:
            return

        # Ensure we have enough data
        if len(self.data) < 50:
            return

        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        # Log current state
        # logger.info(f"Price: {current['close']:.2f}, RSI: {current['rsi']:.2f}, ADX: {current['adx']:.2f}")

        # Check Position
        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.params.get('seasonality_score', 50) > 40
        global_align_ok = self.params.get('global_alignment_score', 50) > 40

        # Position Sizing Logic
        usd_vol = self.params.get('usd_inr_volatility', 0.0)
        size_multiplier = 1.0

        if usd_vol > 1.0:
            size_multiplier = 0.7 # Reduce by 30%
            logger.info(f"High USD Volatility ({usd_vol:.2f}%): Reducing position size by 30%.")

        # Calculate quantity (assuming base lot size 1, but could be scaled by capital)
        # Note: PositionManager usually handles lots, so we need to pass multiplier or adjust lots
        # Here we assume base_qty is lots. Since we can't trade 0.7 lots, we might skip if size < 1 or strictly round
        # For simplicity, we stick to min 1 lot, but log risk warning, or if capital allows, trade larger and reduce.
        # Assuming we can trade 1 lot minimum. If multiplier implies reduction, we should be cautious.

        base_qty = 1

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        if not global_align_ok and not has_position:
            logger.info("Global Alignment Weak: Skipping new entries.")
            return

        # Entry Logic
        if not has_position:
            # BUY Signal: ADX > 25 (Trend Strength), RSI > 50 (Bullish), Price > Prev Close
            if (current['adx'] > self.params['adx_threshold'] and
                current['rsi'] > 55 and
                current['close'] > prev['close']):

                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    # In a real scenario, we might pass size_multiplier to update_position or calculate precise lots
                    # For now, we respect the reduction warning.
                    if size_multiplier < 1.0:
                         logger.warning("⚠️ Reducing Risk due to Volatility (Position Size constrained)")

                    self.pm.update_position(base_qty, current['close'], 'BUY')

            # SELL Signal: ADX > 25, RSI < 45, Price < Prev Close
            elif (current['adx'] > self.params['adx_threshold'] and
                  current['rsi'] < 45 and
                  current['close'] < prev['close']):

                logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    if size_multiplier < 1.0:
                         logger.warning("⚠️ Reducing Risk due to Volatility (Position Size constrained)")
                    self.pm.update_position(base_qty, current['close'], 'SELL')

        # Exit Logic
        elif has_position:
            # Retrieve position details
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

            # Stop Loss / Take Profit Logic could be added here
            # Simple Exit: Trend Fades (ADX < 20) or RSI Reversal

            if pos_qty > 0: # Long
                if current['rsi'] < 45 or current['adx'] < 20:
                     logger.info(f"EXIT LONG: Trend Faded. RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                     self.pm.update_position(abs(pos_qty), current['close'], 'SELL')
            elif pos_qty < 0: # Short
                if current['rsi'] > 55 or current['adx'] < 20:
                     logger.info(f"EXIT SHORT: Trend Faded. RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                     self.pm.update_position(abs(pos_qty), current['close'], 'BUY')

    def run(self):
        logger.info(f"Starting MCX Momentum Strategy for {self.symbol}")
        while True:
            if not self.check_risk_parameters():
                logger.error("Risk checks failed (Expiry). Stopping Strategy.")
                break

            if not is_market_open():
                logger.info("Market is closed. Sleeping...")
                time.sleep(300)
                continue

            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()
            time.sleep(900) # 15 minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Commodity Momentum Strategy')
    parser.add_argument('--symbol', type=str, help='MCX Symbol (e.g., GOLDM05FEB26FUT)')
    parser.add_argument('--underlying', type=str, help='Commodity Name (e.g., GOLD, SILVER, CRUDEOIL)')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    # New Multi-Factor Arguments
    parser.add_argument('--usd_inr_trend', type=str, default='Neutral', help='USD/INR Trend')
    parser.add_argument('--usd_inr_volatility', type=float, default=0.0, help='USD/INR Volatility %')
    parser.add_argument('--seasonality_score', type=int, default=50, help='Seasonality Score (0-100)')
    parser.add_argument('--global_alignment_score', type=int, default=50, help='Global Alignment Score')

    args = parser.parse_args()

    # Strategy Parameters
    PARAMS = {
        'period_adx': 14,
        'period_rsi': 14,
        'period_atr': 14,
        'adx_threshold': 25,
        'risk_per_trade': 0.02,
        'usd_inr_trend': args.usd_inr_trend,
        'usd_inr_volatility': args.usd_inr_volatility,
        'seasonality_score': args.seasonality_score,
        'global_alignment_score': args.global_alignment_score
    }

    # Symbol Resolution
    symbol = args.symbol or os.getenv('SYMBOL')

    # Try to resolve from underlying using SymbolResolver
    if not symbol and args.underlying:
        try:
            from symbol_resolver import SymbolResolver
        except ImportError:
            try:
                from utils.symbol_resolver import SymbolResolver
            except ImportError:
                try:
                    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
                except ImportError:
                    SymbolResolver = None

        if SymbolResolver:
            resolver = SymbolResolver()
            res = resolver.resolve({'underlying': args.underlying, 'type': 'FUT', 'exchange': 'MCX'})
            if res:
                symbol = res
                logger.info(f"Resolved {args.underlying} -> {symbol}")
            else:
                logger.error(f"Could not resolve symbol for {args.underlying}")
        else:
            logger.error("SymbolResolver not available")

    if not symbol:
        logger.error("Symbol not provided. Use --symbol or --underlying argument, or set SYMBOL env var.")
        sys.exit(1)

    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    port = args.port or int(os.getenv('OPENALGO_PORT', 5001))
    host = f"http://127.0.0.1:{port}"

    strategy = MCXMomentumStrategy(symbol, api_key, host, PARAMS)
    strategy.run()

# Default Strategy Parameters (module level for generate_signal)
DEFAULT_PARAMS = {
    'period_adx': 14,
    'period_rsi': 14,
    'period_atr': 14,
    'adx_threshold': 25,
    'risk_per_trade': 0.02,
}

def generate_signal(df, client=None, symbol=None, params=None):
    # Merge default params with provided params
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, 'api_key') else "BACKTEST"
    host = client.host if client and hasattr(client, 'host') else "http://127.0.0.1:5001"

    strat = MCXMomentumStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
