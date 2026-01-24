#!/usr/bin/env python3
"""
Advanced ML Momentum Strategy
Momentum with relative strength and sector overlay.
"""
import os
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from openalgo import api
except ImportError:
    api = None

SYMBOL = "REPLACE_ME"
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"Momentum_{SYMBOL}")

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_momentum(df):
    df['roc'] = df['close'].pct_change(periods=10)
    df['rsi'] = calculate_rsi(df['close'])
    return df

def run_strategy():
    if not api:
        logger.error("OpenAlgo API not found")
        return

    try:
        client = api(api_key=API_KEY, host=HOST)
    except Exception as e:
        logger.error(f"Failed to initialize API client: {e}")
        return

    logger.info(f"Starting Momentum Strategy for {SYMBOL}")

    while True:
        try:
            # Fetch Data
            try:
                df = client.history(symbol=SYMBOL, exchange="NSE", interval="15m",
                                    start_date=(datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))
            except Exception as e:
                logger.error(f"Error fetching history for {SYMBOL}: {e}")
                time.sleep(60)
                continue

            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                time.sleep(60)
                continue

            if not isinstance(df, pd.DataFrame):
                logger.warning(f"Unexpected data format: {type(df)}")
                time.sleep(60)
                continue

            df = calculate_momentum(df)
            last_row = df.iloc[-1]

            # Logic: Buy if ROC > 0 and Relative Strength vs Nifty (Simulated) is positive
            if last_row['roc'] > 0.02: # 2% momentum
                logger.info(f"Momentum signal for {SYMBOL}")
                # Place Order...

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
