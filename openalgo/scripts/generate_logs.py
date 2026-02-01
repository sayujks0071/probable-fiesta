#!/usr/bin/env python3
import os
import random
from datetime import datetime, timedelta

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(REPO_ROOT, 'log', 'strategies')

os.makedirs(LOG_DIR, exist_ok=True)

def generate_supertrend_vwap_log():
    # Simulate High Rejection Rate (> 70%)
    # Strategy: supertrend_vwap_strategy
    # Symbol: NIFTY
    filename = os.path.join(LOG_DIR, "supertrend_vwap_strategy_NIFTY.log")

    lines = []
    base_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)

    # 20 Signals, 4 Entries (80% Rejection)
    for i in range(20):
        current_time = base_time + timedelta(minutes=15*i)
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

        # Log a Signal detection (counts as Signal)
        lines.append(f"{timestamp} - VWAP_NIFTY - INFO - Potential Crossover detected. Checking filters...")

        # Only enter 4 times
        if i % 5 == 0:
            lines.append(f"{timestamp} - VWAP_NIFTY - INFO - VWAP Crossover Buy. Price: 21500.00, POC: 21450.00, Vol: 5000, Sector: Bullish, Dev: 0.0050, Qty: 50 (VIX: 14.0)")
            # Simulate a Win later
            exit_time = current_time + timedelta(minutes=30)
            exit_ts = exit_time.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
            lines.append(f"{exit_ts} - VWAP_NIFTY - INFO - Trailing Stop Hit at 21550.00")
            lines.append(f"{exit_ts} - VWAP_NIFTY - INFO - PnL: 2500.0")
        else:
            lines.append(f"{timestamp} - VWAP_NIFTY - INFO - Filter rejected: Volume low or Sector weak.")

    with open(filename, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Generated {filename}")

def generate_ai_hybrid_log():
    # Simulate Low Win Rate (< 60%)
    # Strategy: ai_hybrid_reversion_breakout
    # Symbol: RELIANCE
    filename = os.path.join(LOG_DIR, "ai_hybrid_reversion_breakout_RELIANCE.log")

    lines = []
    base_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)

    # 10 Entries, 3 Wins, 7 Losses (30% WR)
    for i in range(10):
        current_time = base_time + timedelta(minutes=30*i)
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

        # Entry
        lines.append(f"{timestamp} - AIHybrid_RELIANCE - INFO - Oversold Reversion Signal (RSI<30, <LowerBB, Vol>1.2x). BUY.")

        exit_time = current_time + timedelta(minutes=15)
        exit_ts = exit_time.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

        if i < 3: # Win
            lines.append(f"{exit_ts} - AIHybrid_RELIANCE - INFO - Reversion Target Hit (SMA20). PnL: 1500.0")
        else: # Loss
            lines.append(f"{exit_ts} - AIHybrid_RELIANCE - INFO - Stop Loss Hit. PnL: -500.0")

    with open(filename, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Generated {filename}")

if __name__ == "__main__":
    generate_supertrend_vwap_log()
    generate_ai_hybrid_log()
