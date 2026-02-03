import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

# Configure logger
logger = logging.getLogger("MarketAnalysis")

class MarketAnalyzer:
    def __init__(self, api_client):
        self.client = api_client

    def calculate_indicators(self, df):
        """Calculate technical indicators for scoring."""
        if df.empty: return df
        df = df.copy()

        # Trend: SMA, EMA
        df['sma20'] = df['close'].rolling(20).mean()
        df['sma50'] = df['close'].rolling(50).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()

        # Momentum: RSI (Wilder's Smoothing), MACD
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        df['ema12'] = df['close'].ewm(span=12).mean()
        df['ema26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['signal'] = df['macd'].ewm(span=9).mean()

        # Volatility: ATR
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()

        return df

    def get_trend_score(self, df):
        """Max Score: 20"""
        if df.empty or len(df) < 50: return 0
        last = df.iloc[-1]
        score = 0

        # SMA Alignment (10 pts)
        if last['close'] > last['sma20'] > last['sma50']:
            score += 10
        elif last['close'] > last['sma20']:
            score += 5

        # EMA Trend (5 pts)
        if last['close'] > last['ema20']:
            score += 5

        # Slope/Strength (5 pts)
        # Check if SMA20 is rising
        try:
            prev_sma = df.iloc[-5]['sma20']
            if last['sma20'] > prev_sma:
                score += 5
        except: pass

        return min(20, score)

    def get_momentum_score(self, df):
        """Max Score: 20"""
        if df.empty: return 0
        last = df.iloc[-1]
        score = 0

        # RSI (10 pts)
        rsi = last['rsi']
        if 50 <= rsi <= 70:
            score += 10 # Sweet spot
        elif rsi > 70:
            score += 5 # Strong but overbought
        elif 40 < rsi < 50:
            score += 2 # Recovering

        # MACD (10 pts)
        if last['macd'] > last['signal']:
            score += 10

        return min(20, score)

    def get_volume_score(self, df):
        """Max Score: 15"""
        if df.empty: return 0
        last = df.iloc[-1]
        avg_vol = df['volume'].rolling(20).mean().iloc[-1]

        score = 0
        if last['volume'] > avg_vol:
            score += 10
        if last['volume'] > avg_vol * 1.5:
            score += 5

        return min(15, score)

    def get_volatility_score(self, df, vix=15):
        """Max Score: 10"""
        # In high VIX, we penalize unless strategy is specific?
        # General equity score prefers stable volatility

        if vix > 25: return 2 # Penalty for high market fear

        # Check if ATR is not exploding (volatility contraction is good for breakout, expansion for momentum)
        # We'll assume moderate is good
        return 8

    def get_sector_score(self, sector_df, stock_df):
        """Max Score: 10"""
        if sector_df is None or sector_df.empty: return 5 # Neutral

        try:
            stock_roc = stock_df['close'].pct_change(10).iloc[-1]
            sector_roc = sector_df['close'].pct_change(10).iloc[-1]

            if stock_roc > sector_roc: return 10 # Outperforming
            if stock_roc > 0 and sector_roc > 0: return 7 # Both up
        except:
            pass

        return 5

    def calculate_composite_score(self, symbol, df, sector_df=None, vix=15, market_breadth=0.5):
        """
        Calculate Composite Score (0-100)
        """
        df = self.calculate_indicators(df)

        trend = self.get_trend_score(df)      # Max 20
        mom = self.get_momentum_score(df)     # Max 20
        vol = self.get_volume_score(df)       # Max 15
        vola = self.get_volatility_score(df, vix) # Max 10

        sec = self.get_sector_score(sector_df, df) # Max 10

        # Market Breadth Score (Max 10)
        # A/D Ratio > 1.0 => 10, > 0.5 => 5, else 0
        breadth_score = 10 if market_breadth >= 1.0 else (5 if market_breadth >= 0.7 else 0)

        # News Sentiment (Max 10) - Mocked
        sent_score = 5

        # Liquidity (Max 5)
        # Assume liquid if passed here (filtering done before)
        liq_score = 5

        total = trend + mom + vol + vola + sec + breadth_score + sent_score + liq_score

        # Cap at 100
        total = min(100, total)

        return total, {
            'Trend': trend,
            'Momentum': mom,
            'Volume': vol,
            'Volatility': vola,
            'Sector': sec,
            'Breadth': breadth_score,
            'Sentiment': sent_score,
            'Liquidity': liq_score
        }
