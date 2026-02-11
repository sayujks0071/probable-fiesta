import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_trend_data(n_bars=2000, start_price=100.0, volatility=0.01, trend_slope=0.0005):
    """
    Generate synthetic trending data.
    """
    np.random.seed(42)

    # Generate geometric brownian motion with positive drift
    returns = np.random.normal(loc=trend_slope, scale=volatility, size=n_bars)
    price_path = start_price * np.exp(np.cumsum(returns))

    data = []
    start_time = datetime.now() - timedelta(minutes=15 * n_bars)

    for i in range(n_bars):
        close = price_path[i]
        # Create realistic OHLC bars around close
        daily_vol = close * volatility

        # Randomize Open/High/Low
        open_p = close * (1 + np.random.normal(0, 0.001))
        high_p = max(open_p, close) * (1 + abs(np.random.normal(0, 0.002)))
        low_p = min(open_p, close) * (1 - abs(np.random.normal(0, 0.002)))
        volume = int(np.random.normal(10000, 2000))

        timestamp = start_time + timedelta(minutes=15 * i)

        data.append({
            'timestamp': timestamp,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close,
            'volume': max(100, volume)
        })

    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df

def generate_range_data(n_bars=2000, start_price=100.0, volatility=0.01, amplitude=5.0):
    """
    Generate synthetic range-bound data (Sine wave).
    """
    np.random.seed(42)

    # Sine wave component
    x = np.linspace(0, 8 * np.pi, n_bars)
    sine_wave = amplitude * np.sin(x)

    # Noise component
    noise = np.random.normal(0, start_price * volatility, n_bars)

    price_path = start_price + sine_wave + noise

    data = []
    start_time = datetime.now() - timedelta(minutes=15 * n_bars)

    for i in range(n_bars):
        close = price_path[i]
        # Create realistic OHLC bars around close
        open_p = close * (1 + np.random.normal(0, 0.001))
        high_p = max(open_p, close) + abs(np.random.normal(0, start_price * volatility * 0.2))
        low_p = min(open_p, close) - abs(np.random.normal(0, start_price * volatility * 0.2))
        volume = int(np.random.normal(8000, 1500))

        timestamp = start_time + timedelta(minutes=15 * i)

        data.append({
            'timestamp': timestamp,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close,
            'volume': max(100, volume)
        })

    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df
