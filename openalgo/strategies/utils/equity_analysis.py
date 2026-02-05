"""
Equity Analysis Utility Module
Implements multi-factor analysis, scoring, and market data fetching for NSE Equities.
"""
import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from openalgo.strategies.utils.trading_utils import APIClient, is_market_open, normalize_symbol
except ImportError:
    try:
        from .trading_utils import APIClient, is_market_open, normalize_symbol
    except ImportError:
        try:
            # Fallback for when utils is in path (e.g. from scripts)
            from trading_utils import APIClient, is_market_open, normalize_symbol
        except ImportError:
            # Fallback for direct execution
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from utils.trading_utils import APIClient, is_market_open, normalize_symbol

class EquityAnalyzer:
    def __init__(self, api_key=None, host=None, client=None):
        self.logger = logging.getLogger("EquityAnalyzer")
        if client:
            self.client = client
        else:
            self.api_key = api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
            self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
            self.client = APIClient(api_key=self.api_key, host=self.host)

    def fetch_data(self, symbol, interval="15m", period_days=5, exchange=None):
        """Fetch historical data for a symbol."""
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")

            if not exchange:
                exchange = "NSE_INDEX" if "NIFTY" in symbol.upper() or "VIX" in symbol.upper() else "NSE"

            df = self.client.history(symbol=symbol, interval=interval, exchange=exchange,
                                     start_date=start_date, end_date=end_date)
            return df
        except Exception as e:
            self.logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def calculate_atr(self, df, period=14):
        if df.empty: return 0.0
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def calculate_adx(self, df, period=14):
        if df.empty: return 0.0
        try:
            plus_dm = df['high'].diff()
            minus_dm = df['low'].diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm > 0] = 0

            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['close'].shift(1)).abs()
            tr3 = (df['low'] - df['close'].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            atr = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
            minus_di = 100 * (minus_dm.abs().ewm(alpha=1/period).mean() / atr)
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
            adx = dx.rolling(period).mean().iloc[-1]
            return 0.0 if np.isnan(adx) else adx
        except:
            return 0.0

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def analyze_volume_profile(self, df, n_bins=20):
        """Calculate POC (Point of Control) Price and Volume."""
        if df.empty: return 0.0, 0.0
        price_min = df['low'].min()
        price_max = df['high'].max()
        if price_min == price_max: return df['close'].iloc[-1], 0.0

        bins = np.linspace(price_min, price_max, n_bins)
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)
        volume_profile = df.groupby('bin')['volume'].sum()

        if volume_profile.empty: return 0.0, 0.0

        poc_bin = volume_profile.idxmax()
        poc_volume = volume_profile.max()

        if pd.isna(poc_bin): return 0.0, 0.0

        poc_bin = int(poc_bin)
        # Handle bin edge case
        if poc_bin >= len(bins)-1: poc_bin = len(bins)-2

        poc_price = bins[poc_bin] + (bins[1] - bins[0]) / 2
        return poc_price, poc_volume

    def get_market_regime(self):
        """
        Determine market regime based on VIX and NIFTY Trend.
        Returns: 'TRENDING', 'RANGING', 'VOLATILE'
        """
        vix_df = self.fetch_data("INDIA VIX", interval="1d", period_days=5)
        nifty_df = self.fetch_data("NIFTY 50", interval="1d", period_days=10)

        vix = 15.0
        if not vix_df.empty:
            vix = vix_df['close'].iloc[-1]

        is_trending = False
        if not nifty_df.empty and len(nifty_df) > 5:
            sma5 = nifty_df['close'].rolling(5).mean().iloc[-1]
            price = nifty_df['close'].iloc[-1]
            if abs(price - sma5) / sma5 > 0.01: # 1% away from SMA5
                is_trending = True

        if vix > 20:
            return 'VOLATILE'
        elif is_trending:
            return 'TRENDING'
        else:
            return 'RANGING'

    def get_market_breadth(self):
        """
        Get Market Breadth proxy (0.0 to 1.0).
        Uses NIFTY 50 and NIFTY BANK trend alignment.
        """
        nifty = self.fetch_data("NIFTY 50", interval="1d", period_days=10)
        bank = self.fetch_data("NIFTY BANK", interval="1d", period_days=10)

        score = 0.5

        if not nifty.empty:
            if nifty['close'].iloc[-1] > nifty['close'].iloc[0]: score += 0.2
            else: score -= 0.2

        if not bank.empty:
            if bank['close'].iloc[-1] > bank['close'].iloc[0]: score += 0.2
            else: score -= 0.2

        return max(0.0, min(1.0, score))

    def get_sector_strength(self, sector_symbol):
        """Check if a sector is strong (Price > SMA20)."""
        df = self.fetch_data(sector_symbol, interval="1d", period_days=30)
        if df.empty or len(df) < 20: return 0.5 # Neutral

        df['sma20'] = df['close'].rolling(20).mean()
        last = df.iloc[-1]

        if last['close'] > last['sma20']:
            return 1.0 # Strong
        else:
            return 0.0 # Weak

    def calculate_composite_score(self, symbol, strategy_type='MOMENTUM', sector=None):
        """
        Calculate Composite Score (0-100) based on factors.
        """
        df = self.fetch_data(symbol, interval="15m", period_days=5)
        if df.empty or len(df) < 50: return 0

        last = df.iloc[-1]

        # 1. Trend Score (20%)
        adx = self.calculate_adx(df)
        df['sma50'] = df['close'].rolling(50).mean()
        is_uptrend = last['close'] > df['sma50'].iloc[-1]
        trend_score = 0
        if is_uptrend:
            if adx > 25: trend_score = 100
            else: trend_score = 50
        else:
            trend_score = 0

        # 2. Momentum Score (20%)
        df['rsi'] = self.calculate_rsi(df['close'])
        rsi = df['rsi'].iloc[-1]
        momentum_score = 0
        if 50 < rsi < 70: momentum_score = 100
        elif rsi > 70: momentum_score = 80 # Overbought but strong
        elif rsi < 30: momentum_score = 20 # Oversold
        else: momentum_score = 50

        # 3. Volume Score (15%)
        vol_avg = df['volume'].rolling(20).mean().iloc[-1]
        vol_score = 0
        if last['volume'] > vol_avg * 1.5: vol_score = 100
        elif last['volume'] > vol_avg: vol_score = 75
        else: vol_score = 25

        # 4. Volatility Score (10%)
        # Lower volatility (ATR) relative to price might be better for some, but here maybe controlled vol?
        # Let's say we prefer stable ATR, not exploding.
        # Placeholder logic:
        volatility_score = 50 # Neutral default

        # 5. Sector Strength (10%)
        sector_score = 50
        if sector:
            if self.get_sector_strength(sector) > 0.5:
                sector_score = 100
            else:
                sector_score = 0

        # 6. Breadth (10%) - Mocked or fetched via index
        breadth_score = 50
        regime = self.get_market_regime()
        if regime == 'TRENDING': breadth_score = 100
        elif regime == 'RANGING': breadth_score = 50
        else: breadth_score = 0

        # 7. Sentiment (10%) - Placeholder
        sentiment_score = 50

        # 8. Liquidity (5%)
        liquidity_score = 100 # Assuming liquid if in watchlist

        # Weighted Sum
        composite = (
            (trend_score * 0.20) +
            (momentum_score * 0.20) +
            (vol_score * 0.15) +
            (volatility_score * 0.10) +
            (sector_score * 0.10) +
            (breadth_score * 0.10) +
            (sentiment_score * 0.10) +
            (liquidity_score * 0.05)
        )

        return composite
