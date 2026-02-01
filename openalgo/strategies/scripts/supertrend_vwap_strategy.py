#!/usr/bin/env python3
"""
[Optimization 2026-02-01] Integrated RiskManager & Consolidated Logic
SuperTrend VWAP Strategy
"""
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
    from trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient, normalize_symbol, SmartOrder
    from risk_manager import RiskManager, EODSquareOff
    from symbol_resolver import SymbolResolver
    from constants import DEFAULT_API_HOST
    # Optional Observability
    try:
        from openalgo_observability.logging_setup import setup_logging
        setup_logging()
    except ImportError:
        pass
except ImportError as e:
    print(f"Import Error: {e}")
    # Don't exit if strictly importing for backtest
    pass

class SuperTrendVWAPStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False, sector_benchmark='NIFTY BANK', logfile=None, client=None):
        self.symbol = normalize_symbol(symbol)
        self.quantity = quantity
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY')
        self.host = host or os.getenv('OPENALGO_HOST', DEFAULT_API_HOST)
        self.ignore_time = ignore_time
        self.sector_benchmark = sector_benchmark

        # Strategy Parameters
        self.adx_threshold = 20
        self.adx_period = 14
        self.atr_period = 14
        self.atr_sl_multiplier = 3.0

        # Setup Logging
        self.logger = logging.getLogger(f"VWAP_{self.symbol}")
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
            if logfile:
                fh = logging.FileHandler(logfile)
                fh.setFormatter(formatter)
                self.logger.addHandler(fh)

        # Initialize Client
        self.client = client if client else APIClient(api_key=self.api_key, host=self.host)
        self.smart_order = SmartOrder(self.client)

        # Initialize Risk Manager
        self.risk_manager = RiskManager(
            strategy_name=f"SuperTrendVWAP_{self.symbol}",
            exchange="NSE", # Default, updated in run() if needed
            capital=500000
        )

        # EOD Handler
        self.eod_handler = EODSquareOff(self.risk_manager, self.execute_trade, api_client=self.client)

        # State
        self.atr = 0.0

    def execute_trade(self, symbol, action, quantity):
        """Callback for EOD Square-off and general execution"""
        # Determine exchange based on symbol
        exchange = "NSE"
        if "NIFTY" in symbol or "BANKNIFTY" in symbol: exchange = "NFO" # Options/Futures
        if symbol.endswith('FUT') and "NIFTY" not in symbol: exchange = "MCX"

        return self.smart_order.place_adaptive_order(
            strategy="SuperTrendVWAP",
            symbol=symbol,
            action=action,
            exchange=exchange,
            quantity=quantity
        )

    def calculate_indicators(self, df):
        if df.empty: return df
        df = calculate_intraday_vwap(df)

        # ATR
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        self.atr = tr.rolling(self.atr_period).mean().iloc[-1]

        # ADX
        try:
            plus_dm = high.diff()
            minus_dm = low.diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm > 0] = 0

            atr_series = tr.rolling(self.adx_period).mean()
            plus_di = 100 * (plus_dm.ewm(alpha=1/self.adx_period).mean() / atr_series)
            minus_di = 100 * (minus_dm.abs().ewm(alpha=1/self.adx_period).mean() / atr_series)
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
            df['adx'] = dx.rolling(self.adx_period).mean()
        except:
            df['adx'] = 0

        return df

    def generate_signal(self, df):
        """Core Logic"""
        if df.empty: return 'HOLD', {}, {}

        last = df.iloc[-1]

        # Volume Profile Analysis
        poc_price, _ = self.analyze_volume_profile(df)

        # Conditions
        is_above_vwap = last['close'] > last['vwap']

        vol_mean = df['volume'].rolling(20).mean().iloc[-1]
        vol_std = df['volume'].rolling(20).std().iloc[-1]
        is_volume_spike = last['volume'] > (vol_mean + 1.5 * vol_std)

        is_above_poc = last['close'] > poc_price

        dev_threshold = 0.02 # Simplified
        is_not_overextended = abs(last['vwap_dev']) < dev_threshold

        adx_val = last.get('adx', 0)
        is_strong_trend = adx_val > self.adx_threshold

        details = {
            'close': last['close'],
            'vwap': last['vwap'],
            'adx': adx_val,
            'poc': poc_price
        }

        if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and is_strong_trend:
            return 'BUY', 1.0, details

        return 'HOLD', 0.0, details

    def analyze_volume_profile(self, df, n_bins=20):
        try:
            price_min = df['low'].min()
            price_max = df['high'].max()
            if price_min == price_max: return 0, 0
            bins = np.linspace(price_min, price_max, n_bins)
            bin_series = pd.cut(df['close'], bins=bins, labels=False)
            volume_profile = df.groupby(bin_series)['volume'].sum()
            if volume_profile.empty: return 0, 0
            poc_bin = volume_profile.idxmax()
            poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2
            return poc_price, volume_profile.max()
        except:
            return 0, 0

    def run(self):
        self.logger.info(f"Starting Strategy for {self.symbol}")
        exchange = "NSE" # Default
        if "NIFTY" in self.symbol or "BANKNIFTY" in self.symbol: exchange = "NSE_INDEX"
        # MCX logic
        if self.symbol.endswith('FUT') and not "NIFTY" in self.symbol: exchange = "MCX"

        self.risk_manager.exchange = exchange

        while True:
            try:
                # EOD Check
                if self.eod_handler.check_and_execute():
                    self.logger.info("EOD Square-off completed. Sleeping until restart.")
                    time.sleep(3600)
                    continue

                if not self.ignore_time and not is_market_open(exchange):
                    self.logger.info("Market Closed. Waiting...")
                    time.sleep(60)
                    continue

                # Fetch Data
                df = self.client.history(self.symbol, exchange, "5m",
                                       start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                                       end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or len(df) < 50:
                    time.sleep(60)
                    continue

                df = self.calculate_indicators(df)
                last = df.iloc[-1]
                current_price = last['close']

                # Risk Management: Check Stops
                positions = self.risk_manager.get_open_positions()
                if self.symbol in positions:
                    # Update Trailing Stop
                    self.risk_manager.update_trailing_stop(self.symbol, current_price)

                    # Check Exit Conditions (Stop Loss)
                    stop_hit, reason = self.risk_manager.check_stop_loss(self.symbol, current_price)
                    if stop_hit:
                        self.logger.info(f"Exit Trigger: {reason}")
                        res = self.execute_trade(self.symbol, "SELL", abs(positions[self.symbol]['qty']))
                        if res and res.get('status') == 'success':
                            self.risk_manager.register_exit(self.symbol, current_price)

                    # Technical Exit (Close below VWAP)
                    elif current_price < last['vwap']:
                         self.logger.info(f"Technical Exit: Price {current_price} below VWAP {last['vwap']}")
                         res = self.execute_trade(self.symbol, "SELL", abs(positions[self.symbol]['qty']))
                         if res and res.get('status') == 'success':
                            self.risk_manager.register_exit(self.symbol, current_price)

                else:
                    # Entry Logic
                    signal, score, details = self.generate_signal(df)
                    if signal == 'BUY':
                        # Risk Check
                        can_trade, reason = self.risk_manager.can_trade()
                        if can_trade:
                            self.logger.info(f"Entry Signal: {details}")
                            res = self.execute_trade(self.symbol, "BUY", self.quantity)
                            if res and res.get('status') == 'success':
                                sl_price = current_price - (self.atr * self.atr_sl_multiplier)
                                self.risk_manager.register_entry(self.symbol, self.quantity, current_price, "LONG", stop_loss=sl_price)
                        else:
                            self.logger.warning(f"Trade Blocked: {reason}")

            except Exception as e:
                self.logger.error(f"Strategy Error: {e}", exc_info=True)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, help="Trading Symbol")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, help="API Key")
    parser.add_argument("--host", type=str, help="Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
    parser.add_argument("--logfile", type=str, help="Log file")

    args = parser.parse_args()

    if not args.symbol:
        print("Error: --symbol is required")
        return

    strategy = SuperTrendVWAPStrategy(
        symbol=args.symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host,
        ignore_time=args.ignore_time,
        logfile=args.logfile
    )
    strategy.run()

if __name__ == "__main__":
    run_strategy()
