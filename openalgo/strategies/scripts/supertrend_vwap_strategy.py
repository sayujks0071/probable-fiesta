#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis, Enhanced Sector RSI Filter, and Dynamic Risk using EquityAnalyzer.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add repo root to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.equity_analysis import EquityAnalyzer
    from openalgo.strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient, normalize_symbol
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../utils'))
        from equity_analysis import EquityAnalyzer
        from trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient, normalize_symbol
        from symbol_resolver import SymbolResolver
    except ImportError:
        print("Warning: openalgo package not found or imports failed.")
        APIClient = None
        PositionManager = None
        SymbolResolver = None
        EquityAnalyzer = None
        normalize_symbol = lambda s: s
        is_market_open = lambda: True
        calculate_intraday_vwap = lambda df: df

class SuperTrendVWAPStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False, sector_benchmark='NIFTY BANK', logfile=None, client=None):
        self.symbol = symbol
        self.quantity = quantity
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY')
        if not self.api_key and not client:
            raise ValueError("API Key must be provided via --api_key or OPENALGO_APIKEY env var")

        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
        self.ignore_time = ignore_time
        self.sector_benchmark = sector_benchmark

        if client:
            self.client = client
        else:
            self.client = APIClient(api_key=self.api_key, host=self.host)

        # Initialize EquityAnalyzer
        self.analyzer = EquityAnalyzer(client=self.client)

        self.pm = PositionManager(symbol) if PositionManager else None

        # Parameters
        self.threshold = 150
        self.stop_pct = 1.8
        self.adx_threshold = 20
        self.adx_period = 14
        self.trailing_stop = 0.0
        self.atr = 0.0

        # Setup Logger
        self.logger = logging.getLogger(f"VWAP_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        if logfile:
            fh = logging.FileHandler(logfile)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def generate_signal(self, df):
        """Generate signal for backtesting."""
        if df.empty: return 'HOLD', {}, {}

        # Ensure datetime sorted
        df = df.sort_index()

        # Calculate Indicators
        try:
            df = calculate_intraday_vwap(df)
        except:
            return 'HOLD', {}, {}

        self.atr = self.analyzer.calculate_atr(df)
        last = df.iloc[-1]

        # Volume Profile via Analyzer
        poc_price, poc_vol = self.analyzer.analyze_volume_profile(df)

        # Dynamic Deviation (Simulated for backtest or use fetched VIX)
        vix = 15.0 # Mock
        dev_threshold = 0.02
        if vix > 20: dev_threshold = 0.01

        # Logic
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        is_uptrend = True
        if not pd.isna(last.get('ema200')):
            is_uptrend = last['close'] > last['ema200']

        is_above_vwap = last['close'] > last['vwap']
        is_above_poc = last['close'] > poc_price

        adx = self.analyzer.calculate_adx(df)
        is_strong_trend = adx > self.adx_threshold

        score = 0
        details = {'close': last['close'], 'vwap': last['vwap'], 'atr': self.atr, 'poc': poc_price, 'adx': adx}

        if is_above_vwap and is_above_poc and is_strong_trend and is_uptrend:
            return 'BUY', 1.0, details

        return 'HOLD', 0.0, details

    def run(self):
        self.symbol = normalize_symbol(self.symbol)
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol}")

        while True:
            try:
                if not self.ignore_time and not is_market_open():
                    time.sleep(60)
                    continue

                # Fetch via Client (Analyzer method requires period_days=5 which might be too much for 5m interval high freq loop?
                # But here we need intraday history for VWAP. Analyzer defaults to 15m.
                # VWAP calculation needs 'date' based resetting, usually on 1m or 5m data.

                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
                df = self.client.history(
                    symbol=self.symbol, interval="5m", exchange=exchange,
                    start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d"),
                )

                if df.empty or len(df) < 50:
                    time.sleep(60)
                    continue

                # Preprocess
                if "datetime" in df.columns: df["datetime"] = pd.to_datetime(df["datetime"])
                elif "timestamp" in df.columns: df["datetime"] = pd.to_datetime(df["timestamp"])
                else: df["datetime"] = pd.to_datetime(df.index)
                df = df.sort_values("datetime")

                df = calculate_intraday_vwap(df)
                self.atr = self.analyzer.calculate_atr(df)
                last = df.iloc[-1]

                # Volume Profile via Analyzer
                poc_price, poc_vol = self.analyzer.analyze_volume_profile(df)

                # Dynamic Deviation based on VIX (via Analyzer or get_market_regime)
                regime = self.analyzer.get_market_regime()
                dev_threshold = 0.02
                size_multiplier = 1.0

                if regime == 'VOLATILE':
                    dev_threshold = 0.008
                    size_multiplier = 0.5

                # Logic
                is_above_vwap = last['close'] > last['vwap']
                is_above_poc = last['close'] > poc_price

                # Sector Check via Analyzer
                sector_bullish = self.analyzer.get_sector_strength(self.sector_benchmark) > 0.5

                if self.pm and self.pm.has_position():
                    # Manage Position (Trailing Stop)
                    sl_mult = getattr(self, 'ATR_SL_MULTIPLIER', 3.0)
                    if self.trailing_stop == 0:
                        self.trailing_stop = last['close'] - (sl_mult * self.atr)

                    new_stop = last['close'] - (sl_mult * self.atr)
                    if new_stop > self.trailing_stop:
                        self.trailing_stop = new_stop

                    if last['close'] < self.trailing_stop:
                        self.pm.update_position(self.quantity, last['close'], 'SELL')
                        self.trailing_stop = 0.0
                    elif last['close'] < last['vwap']:
                        self.pm.update_position(self.quantity, last['close'], 'SELL')
                        self.trailing_stop = 0.0

                else:
                    # Entry Logic
                    if is_above_vwap and is_above_poc and sector_bullish:
                        # Also check dynamic deviation
                        if abs(last['vwap_dev']) < dev_threshold:
                            adj_qty = int(self.quantity * size_multiplier)
                            if adj_qty < 1: adj_qty = 1
                            self.logger.info(f"VWAP Crossover Buy. Price: {last['close']:.2f}, POC: {poc_price:.2f}. Qty: {adj_qty}")
                            if self.pm:
                                self.pm.update_position(adj_qty, last['close'], 'BUY')
                                sl_mult = getattr(self, 'ATR_SL_MULTIPLIER', 3.0)
                                self.trailing_stop = last['close'] - (sl_mult * self.atr)

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, help="Trading Symbol")
    parser.add_argument("--underlying", type=str, help="Underlying Asset (e.g. NIFTY)")
    parser.add_argument("--type", type=str, default="EQUITY", help="Instrument Type")
    parser.add_argument("--exchange", type=str, default="NSE", help="Exchange")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, help="API Key")
    parser.add_argument("--host", type=str, default='http://127.0.0.1:5001', help="Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
    parser.add_argument("--sector", type=str, default="NIFTY BANK", help="Sector Benchmark")
    parser.add_argument("--logfile", type=str, help="Log file path")

    args = parser.parse_args()

    symbol = args.symbol
    if not symbol and args.underlying:
        if SymbolResolver:
            resolver = SymbolResolver()
            res = resolver.resolve({'underlying': args.underlying, 'type': args.type, 'exchange': args.exchange})
            if isinstance(res, dict): symbol = res.get('sample_symbol')
            else: symbol = res

    if not symbol:
        print("Error: Must provide --symbol or --underlying")
        return

    strategy = SuperTrendVWAPStrategy(
        symbol=symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host,
        ignore_time=args.ignore_time,
        sector_benchmark=args.sector,
        logfile=args.logfile
    )
    strategy.run()

# Module level wrapper
def generate_signal(df, client=None, symbol=None, params=None):
    strat = SuperTrendVWAPStrategy(symbol=symbol or "TEST", quantity=1, api_key="test", host="test", client=client)
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())
    if params:
        if 'threshold' in params: strat.threshold = params['threshold']
        if 'stop_pct' in params: strat.stop_pct = params['stop_pct']
        if 'adx_threshold' in params: strat.adx_threshold = params['adx_threshold']

    setattr(strat, 'BREAKEVEN_TRIGGER_R', 1.5)
    setattr(strat, 'ATR_SL_MULTIPLIER', 3.0)
    setattr(strat, 'ATR_TP_MULTIPLIER', 5.0)

    action, score, details = strat.generate_signal(df)
    return action, score, details

if __name__ == "__main__":
    run_strategy()
