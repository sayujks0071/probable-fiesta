#!/usr/bin/env python3
import os
import random
from datetime import datetime, timedelta

LOG_DIR = os.path.join("openalgo", "log", "strategies")
os.makedirs(LOG_DIR, exist_ok=True)

def generate_log_line(logger_name, level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    return f"{timestamp} - {logger_name} - {level} - {message}\n"

def create_supertrend_log():
    filename = os.path.join(LOG_DIR, "supertrend_vwap_strategy_NIFTY.log")
    logger_name = "VWAP_NIFTY"

    with open(filename, 'w') as f:
        # 40 Rejected Signals
        for i in range(40):
            f.write(generate_log_line(logger_name, "INFO", "Signal Detected: VWAP Crossover (Filters Failed)"))

        # 10 Accepted Entries
        for i in range(10):
            f.write(generate_log_line(logger_name, "INFO", "Signal Detected: VWAP Crossover BUY. Price: 10000.0"))
            # Simulate PnL
            if i % 2 == 0:
                f.write(generate_log_line(logger_name, "INFO", "PnL: 500.0"))
            else:
                f.write(generate_log_line(logger_name, "INFO", "PnL: -200.0"))

    print(f"Created {filename}")

def create_ai_hybrid_log():
    filename = os.path.join(LOG_DIR, "ai_hybrid_reversion_breakout_INFY.log")
    logger_name = "AIHybrid_INFY"

    with open(filename, 'w') as f:
        # 20 Entries
        for i in range(20):
            f.write(generate_log_line(logger_name, "INFO", "Signal Detected: Reversion BUY. Price: 1500.0"))

            # 8 Wins, 12 Losses (WR 40%)
            if i < 8:
                f.write(generate_log_line(logger_name, "INFO", "PnL: 1000.0")) # Win
            else:
                f.write(generate_log_line(logger_name, "INFO", "PnL: -500.0")) # Loss

    print(f"Created {filename}")

if __name__ == "__main__":
    create_supertrend_log()
    create_ai_hybrid_log()
