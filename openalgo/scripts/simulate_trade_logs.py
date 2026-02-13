#!/usr/bin/env python3
import os
import random
from datetime import datetime

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(REPO_ROOT, 'log', 'strategies')

os.makedirs(LOG_DIR, exist_ok=True)

def write_log(filename, signals, entries, win_rate, profit_factor, avg_win, avg_loss, errors=0):
    filepath = os.path.join(LOG_DIR, filename)
    print(f"Generating {filepath}...")

    with open(filepath, 'w') as f:
        f.write(f"Strategy Started at {datetime.now()}\n")

        rejections = signals - entries
        wins = int(entries * win_rate)
        losses = entries - wins

        # Distribute events
        events = []
        for _ in range(wins): events.append('WIN')
        for _ in range(losses): events.append('LOSS')
        random.shuffle(events)

        signal_count = 0
        entry_count = 0

        # Interleave signals and entries
        # If High Rejection: Signal, Signal, Signal, Entry...

        rejection_interval = rejections // (entries if entries > 0 else 1)

        for i in range(entries):
            # Write some rejected signals first
            for _ in range(rejection_interval):
                f.write(f"{datetime.now()} - INFO - Signal Detected: LONG (Rejected by Filter)\n")
                signal_count += 1

            # Write Entry
            f.write(f"{datetime.now()} - INFO - Signal Detected: LONG\n")
            signal_count += 1
            f.write(f"{datetime.now()} - INFO - BUY Order Executed at 100.0\n")
            entry_count += 1

            outcome = events[i]
            if outcome == 'WIN':
                pnl = avg_win * random.uniform(0.9, 1.1)
                f.write(f"{datetime.now()} - INFO - Target Hit. PnL: {pnl:.2f}\n")
            else:
                pnl = -avg_loss * random.uniform(0.9, 1.1)
                f.write(f"{datetime.now()} - INFO - Stop Loss Hit. PnL: {pnl:.2f}\n")

        # Remaining rejections
        remaining = signals - signal_count
        for _ in range(remaining):
             f.write(f"{datetime.now()} - INFO - Signal Detected: SHORT (Rejected by Filter)\n")

        for _ in range(errors):
            f.write(f"{datetime.now()} - ERROR - API Connection Failed\n")

# 1. SuperTrend VWAP: Low Win Rate (40%), Normal R:R (1.5) -> Tighten Filters
# Signals: 20, Entries: 15, Wins: 6 (40%), Losses: 9
write_log('supertrend_vwap_strategy_NIFTY.log',
          signals=20, entries=15, win_rate=0.4, profit_factor=1.0,
          avg_win=150, avg_loss=100, errors=0)

# 2. AI Hybrid: High Rejection (80%), Good WR -> Lower Threshold
# Signals: 50, Entries: 10 (20% Entry Rate), Wins: 7 (70%)
write_log('ai_hybrid_reversion_breakout_BANKNIFTY.log',
          signals=50, entries=10, win_rate=0.7, profit_factor=2.0,
          avg_win=200, avg_loss=100, errors=0)

# 3. MCX Momentum: High Win Rate (85%) -> Relax Filters
# Signals: 10, Entries: 8, Wins: 7 (87.5%)
write_log('mcx_commodity_momentum_strategy_SILVERMIC.log',
          signals=10, entries=8, win_rate=0.875, profit_factor=3.0,
          avg_win=300, avg_loss=100, errors=0)

# 4. ML Momentum: Low R:R (0.8) -> Tighten Stop
# Signals: 15, Entries: 12, Wins: 8 (66%), Avg Win: 80, Avg Loss: 100
write_log('advanced_ml_momentum_strategy_RELIANCE.log',
          signals=15, entries=12, win_rate=0.66, profit_factor=1.2, # PF = (8*80)/(4*100) = 640/400 = 1.6
          avg_win=80, avg_loss=100, errors=2)

# 5. Gap Fade: Good Performance -> No Change
# Signals: 5, Entries: 5, Wins: 3 (60%), Avg Win: 150, Avg Loss: 100
write_log('gap_fade_strategy_NIFTY.log',
          signals=5, entries=5, win_rate=0.6, profit_factor=2.25,
          avg_win=150, avg_loss=100, errors=0)
