#!/usr/bin/env python3
import os
import random
from datetime import datetime

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
LOG_DIR = os.path.join(REPO_ROOT, 'openalgo', 'log', 'strategies')

os.makedirs(LOG_DIR, exist_ok=True)

def write_log(filename, lines):
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, 'w') as f:
        f.write("\n".join(lines))
    print(f"Generated {filepath}")

def generate_supertrend_logs():
    # High Rejection Rate (90%)
    # 20 Signals, 2 Entries
    lines = []
    base_time = datetime.now().replace(hour=9, minute=15, second=0)

    for i in range(20):
        lines.append(f"{base_time} - SuperTrend_NIFTY - INFO - Signal detected: Buy Condition Met.")
        if i < 2:
            lines.append(f"{base_time} - SuperTrend_NIFTY - INFO - BUY executed at 18000.")
            # Add some PnL for completeness
            lines.append(f"{base_time} - SuperTrend_NIFTY - INFO - PnL: 50.0")

    write_log("supertrend_vwap_strategy_NIFTY.log", lines)

def generate_ai_hybrid_logs():
    # Low Win Rate (30%)
    # 10 Entries: 3 Wins, 7 Losses
    lines = []
    base_time = datetime.now().replace(hour=9, minute=30, second=0)

    for i in range(10):
        lines.append(f"{base_time} - AIHybrid_RELIANCE - INFO - Oversold Reversion Signal (RSI<30). BUY.")
        if i < 3:
            lines.append(f"{base_time} - AIHybrid_RELIANCE - INFO - PnL: 100.0") # Win
        else:
            lines.append(f"{base_time} - AIHybrid_RELIANCE - INFO - PnL: -50.0") # Loss

    write_log("ai_hybrid_reversion_breakout_RELIANCE.log", lines)

def generate_mcx_momentum_logs():
    # High Win Rate (100%)
    # 5 Entries: 5 Wins
    lines = []
    base_time = datetime.now().replace(hour=10, minute=0, second=0)

    for i in range(5):
        lines.append(f"{base_time} - MCX_Momentum - INFO - BUY SIGNAL: Price=50000, RSI=60, ADX=30")
        lines.append(f"{base_time} - MCX_Momentum - INFO - PnL: 200.0")

    write_log("mcx_commodity_momentum_strategy_GOLD.log", lines)

def generate_gap_fade_logs():
    # Low R:R (0.5)
    # 10 Entries: 6 Wins, 4 Losses (WR 60%)
    # Wins: +10, Losses: -20
    lines = []
    base_time = datetime.now().replace(hour=9, minute=15, second=0)

    for i in range(10):
        lines.append(f"{base_time} - GapFadeStrategy - INFO - Executing PE Buy for 50 qty.")
        if i < 6:
            lines.append(f"{base_time} - GapFadeStrategy - INFO - PnL: 10.0")
        else:
            lines.append(f"{base_time} - GapFadeStrategy - INFO - PnL: -20.0")

    write_log("gap_fade_strategy_BANKNIFTY.log", lines)

if __name__ == "__main__":
    generate_supertrend_logs()
    generate_ai_hybrid_logs()
    generate_mcx_momentum_logs()
    generate_gap_fade_logs()
