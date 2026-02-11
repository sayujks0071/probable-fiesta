"""
Market Data Manager - Centralized Market Context and Data Fetching

This module provides a centralized way to fetch market context data like VIX,
Market Breadth, and Sector Performance, with caching to reduce API load.
"""
import time
import logging
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger("MarketDataManager")

class MarketDataManager:
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.cache_expiry = {
            'vix': 60,          # 1 minute
            'breadth': 300,     # 5 minutes
            'sector': 300       # 5 minutes
        }

    def get_vix(self):
        """Fetch India VIX with caching."""
        now = time.time()
        if 'vix' in self.cache and now - self.cache['vix']['time'] < self.cache_expiry['vix']:
            return self.cache['vix']['value']

        try:
            # Try get_quote first for real-time
            if hasattr(self.client, 'get_quote'):
                quote = self.client.get_quote("INDIA VIX", "NSE")
                if quote and 'ltp' in quote:
                    vix = float(quote['ltp'])
                    self.cache['vix'] = {'value': vix, 'time': now}
                    return vix

            # Fallback to history
            df = self.client.history("INDIA VIX", exchange="NSE", interval="day",
                                   start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                   end_date=datetime.now().strftime("%Y-%m-%d"))
            if not df.empty:
                vix = df['close'].iloc[-1]
                self.cache['vix'] = {'value': vix, 'time': now}
                return vix
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")

        return 15.0 # Safe default

    def get_breadth(self):
        """Fetch Market Breadth (Nifty 50 Advance/Decline Ratio) with caching."""
        now = time.time()
        if 'breadth' in self.cache and now - self.cache['breadth']['time'] < self.cache_expiry['breadth']:
            return self.cache['breadth']['value']

        try:
            # We use NIFTY 50 trend as a proxy for breadth if individual constituent data isn't available
            # A more advanced implementation would scan all 50 stocks.
            # Here we check if Nifty is > Open and > SMA20
            nifty = self.client.history("NIFTY 50", exchange="NSE", interval="day",
                                      start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                      end_date=datetime.now().strftime("%Y-%m-%d"))

            breadth = 1.0
            if not nifty.empty:
                last = nifty.iloc[-1]
                if last['close'] > last['open']:
                    breadth = 1.5 # Bullish proxy
                else:
                    breadth = 0.8 # Bearish proxy

                self.cache['breadth'] = {'value': breadth, 'time': now}
                return breadth
        except Exception as e:
            logger.warning(f"Breadth fetch failed: {e}")

        return 1.0 # Neutral default

    def get_sector_strength(self, sector_symbol):
        """Check sector strength (Price > SMA20) with caching."""
        cache_key = f"sector_{sector_symbol}"
        now = time.time()
        if cache_key in self.cache and now - self.cache[cache_key]['time'] < self.cache_expiry['sector']:
            return self.cache[cache_key]['value']

        try:
            # Normalize symbol
            exchange = "NSE"
            if "NIFTY" in sector_symbol.upper():
                 exchange = "NSE" # Indices are on NSE in some APIs, NSE_INDEX in others. Let's try NSE first as generic.

            # Check if client supports 'NSE_INDEX'
            # The APIClient in trading_utils defaults to NSE.

            df = self.client.history(symbol=sector_symbol, interval="day", exchange=exchange,
                                start_date=(datetime.now()-timedelta(days=60)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty or len(df) < 20:
                logger.warning(f"Insufficient data for sector {sector_symbol}. Defaulting to True.")
                return True

            df['sma20'] = df['close'].rolling(20).mean()
            last_close = df.iloc[-1]['close']
            last_sma20 = df.iloc[-1]['sma20']

            is_strong = True
            if not pd.isna(last_sma20):
                is_strong = last_close > last_sma20

            self.cache[cache_key] = {'value': is_strong, 'time': now}
            return is_strong

        except Exception as e:
            logger.warning(f"Sector check failed for {sector_symbol}: {e}")
            return True
