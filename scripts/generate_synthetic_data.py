import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

def generate_ohlcv(regime='trend', periods=2000, start_price=1000, volatility=0.01):
    dates = pd.date_range(end=datetime.now(), periods=periods, freq='15min')
    df = pd.DataFrame(index=dates)

    # Base Price movement
    t = np.linspace(0, 4*np.pi, periods)

    if regime == 'trend':
        # Strong Uptrend with pullbacks
        trend = np.linspace(0, 200, periods)
        cycle = 20 * np.sin(t)
        noise = np.random.normal(0, 2, periods)
        price = start_price + trend + cycle + noise
        vol_factor = 1.0

    elif regime == 'range':
        # Sideways
        trend = 0
        cycle = 50 * np.sin(t * 2) # Faster cycles
        noise = np.random.normal(0, 5, periods)
        price = start_price + trend + cycle + noise
        vol_factor = 0.8

    elif regime == 'volatile':
        # High Volatility, Mixed Trend
        trend = np.linspace(0, 50, periods)
        cycle = 100 * np.sin(t * 3)
        noise = np.random.normal(0, 15, periods) # High noise
        price = start_price + trend + cycle + noise
        vol_factor = 2.0

    # Generate OHLC
    # Open is close of previous bar (roughly)
    # High/Low based on volatility

    closes = price
    opens = np.roll(closes, 1)
    opens[0] = closes[0]

    highs = []
    lows = []

    for o, c in zip(opens, closes):
        # Intra-bar volatility
        bar_vol = volatility * vol_factor * o * np.random.uniform(0.5, 1.5)
        h = max(o, c) + (bar_vol * np.random.uniform(0, 1))
        l = min(o, c) - (bar_vol * np.random.uniform(0, 1))
        highs.append(h)
        lows.append(l)

    df['open'] = opens
    df['high'] = highs
    df['low'] = lows
    df['close'] = closes
    df['volume'] = np.random.randint(1000, 50000, periods)

    # Add datetime column for CSV
    df['datetime'] = df.index

    return df

def main():
    output_dir = "openalgo/data/synthetic"
    os.makedirs(output_dir, exist_ok=True)

    regimes = ['trend', 'range', 'volatile']

    for r in regimes:
        print(f"Generating {r} data...")
        df = generate_ohlcv(regime=r, periods=200) # Reduced for speed
        filename = os.path.join(output_dir, f"{r}_data.csv")
        df.to_csv(filename, index=False)
        print(f"Saved to {filename}")

if __name__ == "__main__":
    main()
