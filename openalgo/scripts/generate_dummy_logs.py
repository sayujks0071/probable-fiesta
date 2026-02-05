import os
import random
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'log', 'strategies')
os.makedirs(LOG_DIR, exist_ok=True)

def write_log(filename, signals, entries, wins, losses, avg_win=100, avg_loss=50):
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, 'w') as f:
        f.write(f"Strategy Log for {filename}\n")

        # Write generic signals (rejected ones)
        rejected = signals - entries
        for i in range(rejected):
            f.write(f"{datetime.now()} - INFO - Signal Detected: Potential Setup\n")

        # Write trades
        trades = []
        for _ in range(wins):
            trades.append(('WIN', avg_win))
        for _ in range(losses):
            trades.append(('LOSS', avg_loss))

        random.shuffle(trades)

        for result, amount in trades:
            f.write(f"{datetime.now()} - INFO - Signal Detected: Setup Confirmed\n")
            f.write(f"{datetime.now()} - INFO - BUY Order Executed\n")
            if result == 'WIN':
                pnl = amount
            else:
                pnl = -amount
            f.write(f"{datetime.now()} - INFO - Position Closed. PnL: {pnl}\n")

# 1. SuperTrend VWAP: High Rejection (100 signals, 5 entries)
write_log("supertrend_vwap_strategy_NIFTY.log", signals=100, entries=5, wins=3, losses=2)

# 2. AI Hybrid: Low Win Rate (40%) -> 4 wins, 6 losses
write_log("ai_hybrid_reversion_breakout_RELIANCE.log", signals=20, entries=10, wins=4, losses=6)

# 3. Gap Fade: High Win Rate (90%) -> 9 wins, 1 loss
write_log("gap_fade_strategy_NIFTY.log", signals=15, entries=10, wins=9, losses=1)

# 4. MCX Momentum: Low R:R (0.8) -> Wins=100, Losses=125 (0.8 ratio)
write_log("mcx_commodity_momentum_strategy_GOLD.log", signals=15, entries=10, wins=5, losses=5, avg_win=80, avg_loss=100)

print("Dummy logs generated.")
