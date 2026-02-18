import numpy as np
import pandas as pd
from datetime import datetime, timedelta

class SyntheticDataGenerator:
    """
    Generates synthetic OHLCV data for backtesting strategies across different regimes.
    """
    def __init__(self, start_date="2024-01-01", interval_minutes=15):
        self.start_date = pd.to_datetime(start_date)
        self.interval = timedelta(minutes=interval_minutes)

    def generate_random_walk(self, length=1000, start_price=100.0, mu=0.0, sigma=0.01):
        """
        Generate geometric Brownian motion.
        mu: drift (trend)
        sigma: volatility
        """
        dt = 1.0
        prices = [start_price]
        for _ in range(length - 1):
            shock = np.random.normal(0, 1)
            # price_t = price_{t-1} * exp((mu - 0.5*sigma^2)*dt + sigma*shock)
            change = (mu - 0.5 * sigma**2) * dt + sigma * shock
            price = prices[-1] * np.exp(change)
            prices.append(price)
        return np.array(prices)

    def ohlcv_from_close(self, close_prices, volatility=0.005, volume_base=10000):
        """
        Generate OHLCV from a close price series.
        """
        n = len(close_prices)
        opens = np.zeros(n)
        highs = np.zeros(n)
        lows = np.zeros(n)
        closes = close_prices
        volumes = np.zeros(n)

        # First open is close
        opens[0] = closes[0]

        for i in range(1, n):
            opens[i] = closes[i-1] * (1 + np.random.normal(0, volatility * 0.2)) # Gap risk

        # High and Low derived from Open/Close + noise
        for i in range(n):
            body_max = max(opens[i], closes[i])
            body_min = min(opens[i], closes[i])

            # Wicks
            high_wick = abs(np.random.normal(0, volatility * closes[i]))
            low_wick = abs(np.random.normal(0, volatility * closes[i]))

            highs[i] = body_max + high_wick
            lows[i] = body_min - low_wick

            # Volume correlated with volatility (candle range)
            range_pct = (highs[i] - lows[i]) / opens[i]
            volumes[i] = int(volume_base * (1 + range_pct * 100 + np.random.normal(0, 0.2)))

        # Time index
        times = [self.start_date + i * self.interval for i in range(n)]

        df = pd.DataFrame({
            'datetime': times,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })
        df.set_index('datetime', inplace=True)
        return df

    def generate_regime_data(self, regimes):
        """
        Generate data stitching multiple regimes.
        regimes: list of dicts with keys: 'type' (trend/range), 'length', 'volatility', 'drift'
        """
        all_closes = []
        current_price = 1000.0

        for r in regimes:
            length = r.get('length', 500)
            vol = r.get('volatility', 0.01)
            rtype = r.get('type', 'random')

            if rtype == 'trend_up':
                mu = 0.0002 # Positive drift
            elif rtype == 'trend_down':
                mu = -0.0002 # Negative drift
            elif rtype == 'range':
                mu = 0.0
                # For mean reversion, we might want OU process, but random walk with 0 drift is close enough for simple test
                # Or we can dampen it.
            elif rtype == 'volatile':
                mu = 0.0
                vol *= 3.0 # High volatility
            else:
                mu = 0.0

            # Generate close series
            segment = self.generate_random_walk(length, current_price, mu, vol)
            all_closes.extend(segment)
            current_price = segment[-1]

        # Convert full series to OHLCV
        # Use average volatility for candle formation, or we could vary it per segment.
        # For simplicity, use base volatility.
        return self.ohlcv_from_close(np.array(all_closes), volatility=0.005)
