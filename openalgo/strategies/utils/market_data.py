import yfinance as yf
import requests
from bs4 import BeautifulSoup
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger("MarketDataManager")

class MarketDataManager:
    def __init__(self, client=None):
        self.client = client
        self.cache = {}
        self.cache_expiry = {
            'vix': 60,       # 1 minute
            'gift_nifty': 60, # 1 minute
            'sentiment': 300, # 5 minutes
            'chain': 15      # 15 seconds
        }

    def _is_cache_valid(self, key):
        if key not in self.cache:
            return False
        timestamp, _ = self.cache[key]
        return (time.time() - timestamp) < self.cache_expiry.get(key, 60)

    def get_vix(self):
        """Fetch India VIX."""
        if self._is_cache_valid('vix'):
            return self.cache['vix'][1]

        try:
            # Using yfinance for VIX
            ticker = yf.Ticker("^INDIAVIX")
            hist = ticker.history(period="1d")
            if not hist.empty:
                vix = float(hist['Close'].iloc[-1])
                self.cache['vix'] = (time.time(), vix)
                return vix
            else:
                logger.warning("VIX history empty, returning default 15.0")
                return 15.0
        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            return 15.0

    def get_gift_nifty(self):
        """
        Fetch GIFT Nifty proxy.
        Returns: (price, gap_pct)
        """
        if self._is_cache_valid('gift_nifty'):
            return self.cache['gift_nifty'][1]

        try:
            nifty = yf.Ticker("^NSEI")
            hist = nifty.history(period="5d")

            if hist.empty or len(hist) < 2:
                logger.warning("Nifty history empty or insufficient")
                return 0.0, 0.0

            prev_close = float(hist['Close'].iloc[-2])
            current_price = float(hist['Close'].iloc[-1])

            if prev_close == 0:
                return current_price, 0.0

            gap_pct = ((current_price - prev_close) / prev_close) * 100

            result = (current_price, round(gap_pct, 2))
            self.cache['gift_nifty'] = (time.time(), result)
            return result

        except Exception as e:
            logger.error(f"Error fetching GIFT Nifty: {e}")
            return 0.0, 0.0

    def get_sentiment(self):
        """
        Fetch News Sentiment.
        Returns: (score, label)
        """
        if self._is_cache_valid('sentiment'):
            return self.cache['sentiment'][1]

        try:
            url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
            try:
                response = requests.get(url, timeout=5)
            except:
                return 0.5, "Neutral"

            if response.status_code != 200:
                return 0.5, "Neutral"

            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'up', 'record']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'down', 'weak', 'slump']

            score = 0
            count = 0
            # Analyze titles
            for item in items[:20]:
                title = item.title.text.lower()
                p_count = sum(1 for w in positive_words if w in title)
                n_count = sum(1 for w in negative_words if w in title)

                if p_count > n_count: score += 1
                elif n_count > p_count: score -= 1
                count += 1

            if count == 0:
                result = (0.5, "Neutral")
            else:
                # Normalize logic:
                # Raw score is net positive/negative counts.
                # Map range [-count, count] to [0, 1]
                normalized = (score + count) / (2 * count) if count > 0 else 0.5
                normalized = max(0.0, min(1.0, normalized))

                label = "Neutral"
                if normalized > 0.6: label = "Positive"
                elif normalized < 0.4: label = "Negative"

                result = (round(normalized, 2), label)

            self.cache['sentiment'] = (time.time(), result)
            return result

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return 0.5, "Neutral"

    def get_option_chain(self, symbol, exchange="NSE"):
        if not self.client:
            logger.error("No API client provided")
            return None

        key = f"chain_{symbol}_{exchange}"
        if self._is_cache_valid(key):
            return self.cache[key][1]

        chain = self.client.get_option_chain(symbol, exchange)
        if chain:
            self.cache[key] = (time.time(), chain)
        return chain
