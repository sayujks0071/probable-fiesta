import pandas as pd
import numpy as np
import logging
import os
import sys
from datetime import datetime, timedelta

# Try imports
try:
    from trading_utils import APIClient, normalize_symbol
except ImportError:
    # Fallback
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from trading_utils import APIClient, normalize_symbol
    except ImportError:
        APIClient = None
        normalize_symbol = lambda x: x

class EquityAnalyzer:
    def __init__(self, api_client=None, logger=None):
        self.client = api_client
        self.logger = logger or logging.getLogger("EquityAnalyzer")

    def calculate_trend_score(self, df):
        """
        Calculate Trend Score (0-100).
        ADX > 25: +30
        Price > SMA50: +20
        Price > SMA200: +20
        SMA50 > SMA200: +30
        """
        if df.empty or len(df) < 50: return 50

        score = 0
        last = df.iloc[-1]

        # Calculate ADX
        adx = self._calculate_adx(df)
        if adx > 25: score += 30
        elif adx > 20: score += 15

        # SMAs
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma50

        if last['close'] > sma50: score += 20
        if last['close'] > sma200: score += 20
        if sma50 > sma200: score += 30

        return score

    def calculate_momentum_score(self, df):
        """
        Calculate Momentum Score (0-100).
        RSI (40-70): Bullish Zone
        MACD > Signal: Bullish
        ROC > 0
        """
        if df.empty: return 50
        score = 0
        last = df.iloc[-1]

        # RSI
        rsi = self._calculate_rsi(df)
        if 50 <= rsi <= 70: score += 40
        elif 40 <= rsi < 50: score += 20 # Recovery
        elif rsi > 70: score += 10 # Overbought but strong

        # MACD
        macd, signal, hist = self._calculate_macd(df)
        if macd > signal: score += 30
        if macd > 0: score += 10

        # ROC
        roc = df['close'].pct_change(10).iloc[-1] * 100
        if roc > 2: score += 20
        elif roc > 0: score += 10

        return score

    def calculate_volume_score(self, df):
        """
        Volume Score (0-100).
        Current Vol > Avg Vol
        Price Up + Vol Up
        """
        if df.empty: return 50
        score = 0
        last = df.iloc[-1]

        avg_vol = df['volume'].rolling(20).mean().iloc[-1]
        if avg_vol == 0: return 0

        rel_vol = last['volume'] / avg_vol

        if rel_vol > 2.0: score += 40
        elif rel_vol > 1.2: score += 20

        # Price/Vol Confirmation
        if last['close'] > df['open'].iloc[-1] and last['volume'] > avg_vol:
            score += 40 # Strong buying
        elif last['close'] < df['open'].iloc[-1] and last['volume'] < avg_vol:
            score += 20 # Low vol selling (constructive)

        # Delivery % (Mocked if not in DF, usually not available in OHLC)
        # If 'delivery_volume' in df
        if 'delivery_volume' in df.columns:
            del_pct = (last['delivery_volume'] / last['volume']) * 100
            if del_pct > 50: score += 20

        return min(100, score)

    def calculate_volatility_score(self, df):
        """
        Volatility Score (0-100).
        Lower is usually better for stable trends, but high vol needed for momentum.
        Here we define Score as 'Tradeability'.
        If VIX is high, we want Controlled Volatility.
        Let's use ATR % as a metric.
        """
        if df.empty: return 50
        atr = self._calculate_atr(df)
        price = df['close'].iloc[-1]
        if price == 0: return 50

        atr_pct = (atr / price) * 100

        # Ideal ATR% for swing is 1-3%.
        if 1.0 <= atr_pct <= 3.0: return 100
        if atr_pct < 1.0: return 60 # Too slow
        if atr_pct > 5.0: return 40 # Too volatile
        return 70

    def calculate_sector_score(self, symbol, sector_df=None):
        """
        Relative Strength vs Sector.
        """
        if sector_df is None or sector_df.empty: return 50

        # Simple Logic: Check if Stock ROC > Sector ROC
        # Need history for both. Assuming sector_df is aligned or we fetch it.
        # This function might need refactoring to accept DataFrames directly to avoid API calls inside loop.

        # Placeholder logic if we don't have time-aligned DFs here
        # We assume the caller passes a score or we return neutral
        return 50

    def calculate_composite_score(self, df, market_context=None):
        """
        Composite Score =
         (Trend * 0.20) + (Momentum * 0.20) + (Volume * 0.15) +
         (Volatility * 0.10) + (Sector * 0.10) + (Breadth * 0.10) +
         (Sentiment * 0.10) + (Liquidity * 0.05)
        """
        trend = self.calculate_trend_score(df)
        mom = self.calculate_momentum_score(df)
        vol = self.calculate_volume_score(df)
        vola = self.calculate_volatility_score(df)

        # Context Factors (Default to 50 if missing)
        sector = market_context.get('sector_score', 50) if market_context else 50
        breadth = market_context.get('breadth_score', 50) if market_context else 50
        sent = market_context.get('sentiment_score', 50) if market_context else 50
        liq = 100 # Assume liquid if filtered before

        score = (trend * 0.20) + (mom * 0.20) + (vol * 0.15) + \
                (vola * 0.10) + (sector * 0.10) + (breadth * 0.10) + \
                (sent * 0.10) + (liq * 0.05)

        return score

    def check_earnings(self, symbol, earnings_map=None):
        """
        Check if earnings are within 2 days.
        earnings_map: dict {symbol: date_obj or date_str}
        """
        if not earnings_map: return False

        e_date = earnings_map.get(symbol)
        if not e_date: return False

        if isinstance(e_date, str):
            try:
                e_date = datetime.strptime(e_date, "%Y-%m-%d").date()
            except:
                return False

        days = (e_date - datetime.now().date()).days
        return abs(days) <= 2

    # --- Helpers ---
    def _calculate_adx(self, df, period=14):
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
            return dx.rolling(period).mean().iloc[-1]
        except:
            return 0

    def _calculate_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs)).iloc[-1]

    def _calculate_macd(self, df):
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        return macd.iloc[-1], signal.iloc[-1], hist.iloc[-1]

    def _calculate_atr(self, df, period=14):
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def get_market_breadth(self):
        """
        Calculate Market Breadth (A/D Ratio).
        Requires scanning multiple symbols.
        Returns a score 0-100.
        """
        # This is expensive to do inside a loop. Should be done once by the caller.
        # Placeholder returning neutral.
        return 50
