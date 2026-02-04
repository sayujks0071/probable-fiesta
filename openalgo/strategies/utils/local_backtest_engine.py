import logging
import pandas as pd
import yfinance as yf
from datetime import datetime
import sys
import os

# Ensure we can import SimpleBacktestEngine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Try relative import if package structure allows
    from .simple_backtest_engine import SimpleBacktestEngine

logger = logging.getLogger("LocalBacktestEngine")

class LocalBacktestEngine(SimpleBacktestEngine):
    def __init__(self, initial_capital=1000000.0):
        # Initialize parent but bypass API checks if possible or pass dummies
        # The parent init calls APIClient. We can mock it or let it fail gracefully if we override load_historical_data
        super().__init__(initial_capital=initial_capital, api_key="LOCAL", host="LOCAL")
        self.client = None # Explicitly disable client

    def load_historical_data(self, symbol, exchange, start_date, end_date, interval="15m"):
        """
        Fetch data from yfinance as a proxy for local backtesting.
        """
        yf_symbol = self._map_to_yfinance(symbol, exchange)
        logger.info(f"LocalBacktest: Fetching {yf_symbol} ({interval}) from {start_date} to {end_date}")

        try:
            # yfinance requires specific interval formats
            # 15m is valid.

            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=interval, progress=False)

            if df.empty:
                logger.warning(f"No data returned for {yf_symbol}")
                return pd.DataFrame()

            # Flatten MultiIndex columns if present (yfinance v0.2+)
            if isinstance(df.columns, pd.MultiIndex):
                # We expect (Price, Ticker) -> just Price
                df.columns = df.columns.get_level_values(0)

            # Normalize columns to lowercase
            df.columns = [c.lower() for c in df.columns]

            # Ensure required columns
            required = ['open', 'high', 'low', 'close', 'volume']
            for col in required:
                if col not in df.columns:
                    logger.warning(f"Missing column {col} in yfinance data")

            # Handle index
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            # Localize/Convert to tz-naive if needed to match strategy expectations?
            # Usually strategies expect tz-naive or UTC. yfinance is tz-aware.
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            return df

        except Exception as e:
            logger.error(f"Error fetching data from yfinance: {e}")
            return pd.DataFrame()

    def _map_to_yfinance(self, symbol, exchange):
        # Basic mapping logic
        if symbol == 'NIFTY': return '^NSEI'
        if symbol == 'BANKNIFTY': return '^NSEBANK'

        # Commodities (Global Proxies)
        if 'GOLD' in symbol.upper(): return 'GC=F'
        if 'SILVER' in symbol.upper(): return 'SI=F'
        if 'CRUDE' in symbol.upper(): return 'CL=F'
        if 'NATURALGAS' in symbol.upper(): return 'NG=F'

        # NSE Stocks
        if exchange in ['NSE', 'EQ'] or (exchange == 'NFO' and 'NIFTY' not in symbol):
            if not symbol.endswith('.NS'):
                return f"{symbol}.NS"

        return symbol
