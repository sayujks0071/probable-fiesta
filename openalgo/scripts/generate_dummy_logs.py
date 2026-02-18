import os
import random
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'log', 'strategies')
os.makedirs(LOG_DIR, exist_ok=True)

def generate_log(filename, scenario):
    filepath = os.path.join(LOG_DIR, filename)
    print(f"Generating {filepath} with scenario: {scenario}")

    lines = []

    if scenario == "high_rejection":
        # Many signals, few entries
        for i in range(20):
            lines.append(f"{datetime.now()} - INFO - Signal detected: HOLD (Rejection: Threshold too high)")
        for i in range(2):
            lines.append(f"{datetime.now()} - INFO - Signal detected: BUY. Price: 100.0")
            lines.append(f"{datetime.now()} - INFO - PnL: 50.0") # Win

    elif scenario == "low_win_rate":
        # Many entries, mostly losses
        for i in range(10):
            lines.append(f"{datetime.now()} - INFO - Signal detected: BUY. Price: 100.0")
            if i < 3: # 3 Wins
                lines.append(f"{datetime.now()} - INFO - PnL: 50.0")
            else: # 7 Losses
                lines.append(f"{datetime.now()} - INFO - PnL: -50.0")

    elif scenario == "high_win_rate":
        # Good entries, mostly wins
        for i in range(5):
            lines.append(f"{datetime.now()} - INFO - Signal detected: BUY. Price: 100.0")
            lines.append(f"{datetime.now()} - INFO - PnL: 100.0") # All wins

    elif scenario == "low_rr":
        # Wins are small, losses are big
        for i in range(5):
            lines.append(f"{datetime.now()} - INFO - Signal detected: BUY. Price: 100.0")
            if i < 3: # 3 Wins
                lines.append(f"{datetime.now()} - INFO - PnL: 20.0") # Small Win
            else: # 2 Losses
                lines.append(f"{datetime.now()} - INFO - PnL: -50.0") # Big Loss

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))

if __name__ == "__main__":
    generate_log("supertrend_vwap_strategy_NIFTY.log", "high_rejection")
    generate_log("ai_hybrid_reversion_breakout_RELIANCE.log", "low_win_rate")
    generate_log("mcx_commodity_momentum_strategy_GOLDM05FEB26FUT.log", "high_win_rate")
    generate_log("supertrend_vwap_strategy_BANKNIFTY.log", "low_rr")
