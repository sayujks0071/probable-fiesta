#!/usr/bin/env python3
import sys
import os
import logging
import time
import json
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger("MarketDataManager")

class MarketDataManager:
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.cache_expiry = {
            'vix': 300,        # 5 mins
            'gift_nifty': 300, # 5 mins
            'sentiment': 3600, # 1 hour
            'chain': 60        # 1 min
        }

    def _get_cached(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_expiry.get(key, 60):
                return data
        return None

    def _set_cache(self, key, value):
        self.cache[key] = (value, time.time())

    def get_vix(self):
        """Fetch India VIX."""
        cached = self._get_cached('vix')
        if cached is not None:
            return cached

        vix = 15.0 # Default fallback
        try:
            # Try fetching from broker first if available
            quote = self.client.get_quote("INDIA VIX", "NSE")
            if quote and 'ltp' in quote:
                vix = float(quote['ltp'])
                logger.info(f"Fetched VIX from Broker: {vix}")
            else:
                # Try yfinance
                import yfinance as yf
                ticker = yf.Ticker("^INDIAVIX")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    vix = hist['Close'].iloc[-1]
                    logger.info(f"Fetched VIX from Yahoo: {vix}")
                else:
                    logger.warning("VIX data empty from Yahoo, using default 15.0")
        except ImportError:
            logger.warning("yfinance not installed. Using default VIX 15.0")
        except Exception as e:
            logger.error(f"Error fetching VIX: {e}. Using default 15.0")

        self._set_cache('vix', vix)
        return vix

    def get_gift_nifty(self):
        """Fetch GIFT Nifty (using NSE proxy or similar)."""
        cached = self._get_cached('gift_nifty')
        if cached is not None:
            return cached

        price = 0.0
        gap_pct = 0.0

        try:
            # Try yfinance for ^NSEI as proxy for Nifty 50
            # Ideally we want GIFT Nifty futures, but ^NSEI gives us Nifty Spot close
            # Real GIFT Nifty is usually on SGX/NSE IX, hard to get without paid API.
            # We will use Nifty Spot for now or try to scrape if needed.

            import yfinance as yf
            ticker = yf.Ticker("^NSEI")
            hist = ticker.history(period="2d")

            if len(hist) >= 1:
                last_close = hist['Close'].iloc[-1]
                # In a real scenario, we'd compare this to "current" pre-market price
                # For now, we return the last close as the price
                price = last_close

                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    gap_pct = ((last_close - prev_close) / prev_close) * 100

            logger.info(f"Fetched Nifty Proxy: {price}, Gap (simulated from 2d): {gap_pct:.2f}%")

        except ImportError:
            logger.warning("yfinance not installed. Using 0.0 for GIFT Nifty.")
        except Exception as e:
            logger.error(f"Error fetching GIFT Nifty: {e}")

        result = {'price': price, 'gap_pct': gap_pct}
        self._set_cache('gift_nifty', result)
        return result

    def get_sentiment(self):
        """Fetch News Sentiment from Economic Times RSS."""
        cached = self._get_cached('sentiment')
        if cached is not None:
            return cached

        score = 0.5
        label = "Neutral"

        try:
            url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'xml')
                items = soup.find_all('item')

                positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'up', 'record']
                negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'down', 'fear', 'weak']

                raw_score = 0
                count = 0

                for item in items[:15]: # Check top 15 headlines
                    title = item.title.text.lower()
                    p_count = sum(1 for w in positive_words if w in title)
                    n_count = sum(1 for w in negative_words if w in title)

                    if p_count > n_count: raw_score += 1
                    elif n_count > p_count: raw_score -= 1
                    count += 1

                if count > 0:
                    # Normalize to 0-1 range
                    # -count to +count maps to 0 to 1
                    # score 0 -> 0.5
                    norm = (raw_score / count + 1) / 2
                    score = max(0.0, min(1.0, norm))

                if score > 0.6: label = "Positive"
                elif score < 0.4: label = "Negative"

                logger.info(f"Sentiment Analysis: Score={score:.2f} ({label}) from {count} articles")

        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}")

        result = {'score': score, 'label': label}
        self._set_cache('sentiment', result)
        return result

    def get_option_chain(self, symbol, exchange="NFO"):
        """Fetch Option Chain with Caching."""
        key = f"chain_{symbol}_{exchange}"
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        chain = self.client.get_option_chain(symbol, exchange)
        if chain:
            self._set_cache(key, chain)

        return chain
