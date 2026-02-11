import logging
import requests
from bs4 import BeautifulSoup
import yfinance as yf
from datetime import datetime, timedelta

logger = logging.getLogger("MarketDataManager")

class MarketDataManager:
    def __init__(self, client=None):
        self.client = client
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

    def _get_cached(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return data
        return None

    def _set_cached(self, key, value):
        self.cache[key] = (value, datetime.now())

    def get_vix(self):
        """Get India VIX from API or Yahoo Finance."""
        cached = self._get_cached('vix')
        if cached: return cached

        vix = 15.0  # Default
        try:
            # Try API first
            if self.client:
                q = self.client.get_quote("INDIA VIX", "NSE")
                if q and 'ltp' in q:
                    vix = float(q['ltp'])
                    self._set_cached('vix', vix)
                    return vix

            # Fallback to Yahoo Finance
            ticker = yf.Ticker("^INDIAVIX")
            hist = ticker.history(period="1d")
            if not hist.empty:
                vix = hist['Close'].iloc[-1]
                logger.info(f"Fetched VIX from Yahoo: {vix}")
            else:
                logger.warning("Could not fetch VIX from Yahoo, using default 15.0")

        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")

        self._set_cached('vix', vix)
        return vix

    def get_nifty_gap(self):
        """
        Calculate Nifty Gap % (Current/Open vs Prev Close).
        Returns: (current_price, gap_pct)
        """
        cached = self._get_cached('nifty_gap')
        if cached: return cached

        current_price = 0.0
        gap_pct = 0.0

        try:
            # 1. Get Current Price
            if self.client:
                q = self.client.get_quote("NIFTY 50", "NSE")
                if q and 'ltp' in q:
                    current_price = float(q['ltp'])

            if current_price == 0:
                 # Fallback to Yahoo for current price (delayed)
                 ticker = yf.Ticker("^NSEI")
                 data = ticker.history(period="1d")
                 if not data.empty:
                     current_price = data['Close'].iloc[-1]

            # 2. Get Previous Close
            prev_close = 0.0
            # Try Yahoo history for robust prev close
            ticker = yf.Ticker("^NSEI")
            hist = ticker.history(period="5d") # Get enough days
            if len(hist) >= 2:
                # If market is open, last row is today, so take -2
                # If market is closed/pre-market, last row is yesterday
                # Simple heuristic: compare dates
                last_date = hist.index[-1].date()
                today = datetime.now().date()

                if last_date == today:
                    prev_close = hist['Close'].iloc[-2]
                else:
                    prev_close = hist['Close'].iloc[-1]
            elif not hist.empty:
                 prev_close = hist['Close'].iloc[0]

            if prev_close > 0 and current_price > 0:
                gap_pct = ((current_price - prev_close) / prev_close) * 100

            logger.info(f"Nifty Gap: Current={current_price}, Prev={prev_close}, Gap={gap_pct:.2f}%")

        except Exception as e:
            logger.error(f"Error calculating Nifty Gap: {e}")

        result = (current_price, gap_pct)
        self._set_cached('nifty_gap', result)
        return result

    def get_sentiment(self):
        """
        Scrape news sentiment.
        Returns: (score, label)
        """
        cached = self._get_cached('sentiment')
        if cached: return cached

        score = 0.5
        label = "Neutral"

        try:
            url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
            try:
                response = requests.get(url, timeout=5)
            except:
                return score, label

            if response.status_code != 200:
                return score, label

            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            positive_words = ['surge', 'jump', 'gain', 'rally', 'bull', 'high', 'profit', 'growth', 'buy', 'positive', 'up']
            negative_words = ['fall', 'drop', 'crash', 'bear', 'low', 'loss', 'decline', 'sell', 'negative', 'fear', 'inflation', 'down', 'war']

            raw_score = 0
            count = 0
            for item in items[:15]: # Analyze top 15
                title = item.title.text.lower()
                p_count = sum(1 for w in positive_words if w in title)
                n_count = sum(1 for w in negative_words if w in title)

                if p_count > n_count: raw_score += 1
                elif n_count > p_count: raw_score -= 1
                count += 1

            if count > 0:
                normalized = 0.5 + (raw_score / (2 * count)) # Map -count..count to 0..1
                score = max(0.0, min(1.0, normalized))

            if score > 0.6: label = "Positive"
            elif score < 0.4: label = "Negative"

            logger.info(f"Sentiment Analysis: Score={score:.2f}, Label={label} (based on {count} items)")

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")

        result = (score, label)
        self._set_cached('sentiment', result)
        return result
