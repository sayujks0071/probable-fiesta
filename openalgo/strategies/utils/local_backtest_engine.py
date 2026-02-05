import yfinance as yf
import pandas as pd
import logging
import sys
import os
from datetime import datetime

# Add current directory to path so we can import SimpleBacktestEngine
sys.path.append(os.path.dirname(__file__))
try:
    from simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine

logger = logging.getLogger("LocalBacktestEngine")

class LocalClient:
    def __init__(self, engine):
        self.engine = engine
        self.host = "local"
        self.api_key = "local"

    def history(self, symbol, exchange=None, interval="15m", start_date=None, end_date=None):
        # If dates are None, use defaults?
        if not start_date:
            start_date = "2024-01-01" # Arbitrary default
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Delegate to engine's load_historical_data
        return self.engine.load_historical_data(symbol, exchange, start_date, end_date, interval)

class LocalBacktestEngine(SimpleBacktestEngine):
    def __init__(self, initial_capital=100000.0):
        super().__init__(initial_capital=initial_capital, api_key="local", host="local")
        # Override client with LocalClient to intercept strategy requests (e.g. VIX)
        self.client = LocalClient(self)

    def load_historical_data(self, symbol, exchange, start_date, end_date, interval="15m"):
        # Map symbol
        yf_symbol = self._map_symbol(symbol, exchange)

        # Avoid logging spam for frequent calls (like VIX checks)
        # logger.info(f"Fetching data for {symbol} (Mapped: {yf_symbol}) from yfinance...")

        try:
            # yfinance interval mapping
            yf_interval = interval
            if interval == "15m": yf_interval = "15m"
            elif interval == "5m": yf_interval = "5m"
            elif interval == "1h": yf_interval = "1h"
            elif interval == "1d": yf_interval = "1d"

            # Fetch data
            # Use threads=False to avoid some yfinance issues in some envs, but usually True is fine.
            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=yf_interval, progress=False, auto_adjust=True)

            if df.empty:
                logger.warning(f"No data found for {yf_symbol}")
                return pd.DataFrame()

            # Flatten columns if MultiIndex (yfinance > 0.2.0)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Format columns to lowercase
            df.columns = [c.lower() for c in df.columns]

            # Ensure required columns
            required = ['open', 'high', 'low', 'close', 'volume']
            # Fallback for volume
            if 'volume' not in df.columns:
                df['volume'] = 0

            # Inject fake volume if all zero (common for Indices on Yahoo)
            if (df['volume'] == 0).all():
                 logger.warning(f"Volume is 0 for {yf_symbol}. Injecting fake volume.")
                 import numpy as np
                 df['volume'] = np.random.randint(10000, 50000, size=len(df))

            # Ensure DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            # Sort
            df = df.sort_index()

            return df
        except Exception as e:
            logger.error(f"Error fetching data from yfinance: {e}")
            return pd.DataFrame()

    def _map_symbol(self, symbol, exchange):
        symbol = symbol.upper()

        # Indices
        if symbol == "NIFTY" or symbol == "NIFTY 50":
            return "^NSEI"
        if symbol == "BANKNIFTY" or symbol == "NIFTY BANK":
            return "^NSEBANK"
        if "VIX" in symbol:
            return "^INDIAVIX"

        # MCX / Commodities (Proxies)
        if "SILVER" in symbol:
            return "SI=F"
        if "GOLD" in symbol:
            return "GC=F"
        if "CRUDE" in symbol:
            return "CL=F"
        if "NATURAL" in symbol and "GAS" in symbol:
            return "NG=F"

        # Stocks (Assume NSE)
        if exchange == "NSE" or exchange == "NSE_INDEX":
             if not symbol.endswith(".NS") and "^" not in symbol:
                 return f"{symbol}.NS"

        # MCX default (if not caught above)
        if exchange == "MCX":
             # Best effort guess for US futures if not mapped
             return f"{symbol}=F"

        return symbol
