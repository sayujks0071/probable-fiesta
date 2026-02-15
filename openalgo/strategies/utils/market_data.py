import sys
import os
import logging
import requests
import json
import time
from datetime import datetime, timedelta
import yfinance as yf
from bs4 import BeautifulSoup

logger = logging.getLogger("MarketDataManager")

class MarketDataManager:
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.cache_meta = {}
        # TTL in seconds
        self.ttl_config = {
            "vix": 60,
            "gift_nifty": 300,
            "sentiment": 3600,
            "chain": 15
        }

    def get_vix(self):
        """Fetch INDIA VIX. Prioritize Broker API, fallback to yfinance."""
        cache_key = "vix"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]

        vix = 15.0
        # 1. Try Broker API
        try:
            quote = self.client.get_quote("INDIA VIX", "NSE")
            if quote and 'ltp' in quote:
                vix = float(quote['ltp'])
                self._update_cache(cache_key, vix)
                return vix
        except Exception as e:
            logger.debug(f"Broker VIX fetch failed: {e}")

        # 2. Try yfinance
        try:
            ticker = yf.Ticker("^INDIAVIX")
            hist = ticker.history(period="1d")
            if not hist.empty:
                vix = float(hist['Close'].iloc[-1])
                self._update_cache(cache_key, vix)
                return vix
        except Exception as e:
            logger.debug(f"YFinance VIX fetch failed: {e}")

        self._update_cache(cache_key, vix) # Cache default to avoid spamming
        return vix

    def get_gift_nifty_gap(self):
        """
        Estimate Gap Opening.
        Returns: (gift_price, gap_percent)
        """
        cache_key = "gift_nifty"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]

        # 1. Get Nifty Spot Previous Close
        nifty_prev_close = 0.0
        try:
            # Try Broker Quote first (might have 'close' field)
            quote = self.client.get_quote("NIFTY 50", "NSE")
            if quote and 'close' in quote and quote['close'] > 0:
                nifty_prev_close = float(quote['close'])
            else:
                # Fallback to yfinance
                nifty = yf.Ticker("^NSEI")
                hist = nifty.history(period="5d")
                if len(hist) >= 1:
                    # If fetching during trading day, last row is current.
                    # We want previous day close.
                    if datetime.now().hour >= 9 and len(hist) >= 2:
                         nifty_prev_close = float(hist['Close'].iloc[-2])
                    else:
                         nifty_prev_close = float(hist['Close'].iloc[-1])
        except Exception as e:
            logger.debug(f"Failed to fetch Nifty Prev Close: {e}")

        if nifty_prev_close == 0:
             nifty_prev_close = 24000.0 # Safety default

        # 2. Estimate Current/Opening Price
        current_price = nifty_prev_close # Default no gap

        # Try fetching live price from Broker (if market open or pre-market)
        try:
            quote = self.client.get_quote("NIFTY 50", "NSE")
            if quote and 'ltp' in quote:
                current_price = float(quote['ltp'])
        except:
            pass

        # Calculate Gap
        gap_pct = ((current_price - nifty_prev_close) / nifty_prev_close) * 100

        result = (current_price, gap_pct)
        self._update_cache(cache_key, result)
        return result

    def get_sentiment(self):
        """
        Fetch News Sentiment.
        Returns: (score [0.0-1.0], label [Positive/Neutral/Negative])
        """
        cache_key = "sentiment"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]

        try:
            url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                return 0.5, "Neutral"

            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'record', 'green']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'war', 'tension', 'red']

            score_val = 0
            count = 0
            for item in items[:15]:
                text = (item.title.text + " " + item.description.text).lower()
                p_count = sum(1 for w in positive_words if w in text)
                n_count = sum(1 for w in negative_words if w in text)

                if p_count > n_count: score_val += 1
                elif n_count > p_count: score_val -= 1
                count += 1

            if count == 0:
                result = (0.5, "Neutral")
            else:
                # Normalize from -count..+count to 0..1
                if count > 0:
                     avg_score = score_val / count # -1.0 to 1.0
                else:
                     avg_score = 0

                normalized = (avg_score + 1) / 2 # 0.0 to 1.0

                label = "Neutral"
                if normalized > 0.6: label = "Positive"
                elif normalized < 0.4: label = "Negative"

                result = (round(normalized, 2), label)

            self._update_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            result = (0.5, "Neutral")
            self._update_cache(cache_key, result)
            return result

    def get_option_chain(self, symbol, exchange="NFO"):
        """Fetch Option Chain with caching."""
        key = f"chain_{symbol}_{exchange}"
        if self._is_cache_valid(key):
            return self.cache[key]

        chain = self.client.get_option_chain(symbol, exchange)
        if chain:
            self._update_cache(key, chain)
        return chain

    def _is_cache_valid(self, key):
        if key in self.cache and key in self.cache_meta:
            ts, ttl = self.cache_meta[key]
            if time.time() - ts < ttl:
                return True
        return False

    def _update_cache(self, key, value):
        # Determine TTL
        ttl = self.ttl_config.get(key)
        if not ttl:
            # Handle prefix keys
            if key.startswith("chain_"): ttl = self.ttl_config.get("chain", 15)
            else: ttl = 60

        self.cache[key] = value
        self.cache_meta[key] = (time.time(), ttl)
