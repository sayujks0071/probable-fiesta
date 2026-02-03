import os
import random
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, 'log', 'strategies')
os.makedirs(LOG_DIR, exist_ok=True)

def write_log(filename, events):
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, 'w') as f:
        for event in events:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} - {filename.split('.')[0]} - INFO - {event}\n")
    print(f"Generated {filepath}")

# 1. High Rejection Rate (> 75%), Moderate WR (60%)
# supertrend_vwap_strategy_NIFTY.log
# Signals: 20, Entries: 5. Rejection = 75%.
# Wins: 3, Losses: 2.
events_nifty = []
for _ in range(15):
    events_nifty.append("Signal Rejected: Filter conditions not met")
for _ in range(3):
    events_nifty.append("Signal Crossover Buy. Price: 22000. Qty: 50")
    events_nifty.append("PnL: 500.0 (Win)")
for _ in range(2):
    events_nifty.append("Signal Crossover Buy. Price: 22000. Qty: 50")
    events_nifty.append("PnL: -200.0 (Loss)")

write_log("supertrend_vwap_strategy_NIFTY.log", events_nifty)

# 2. High Win Rate (90%), Low Rejection
# ai_hybrid_reversion_breakout_SBIN.log
# Signals: 10, Entries: 10.
# Wins: 9, Losses: 1.
events_sbin = []
for _ in range(9):
    events_sbin.append("Signal Crossover Buy. Price: 600. Qty: 100")
    events_sbin.append("PnL: 1000.0 (Win)")
for _ in range(1):
    events_sbin.append("Signal Crossover Buy. Price: 600. Qty: 100")
    events_sbin.append("PnL: -200.0 (Loss)")

write_log("ai_hybrid_reversion_breakout_SBIN.log", events_sbin)

# 3. Low Win Rate (40%), Low Rejection
# supertrend_vwap_strategy_RELIANCE.log
# Signals: 10, Entries: 10.
# Wins: 4, Losses: 6.
events_rel = []
for _ in range(4):
    events_rel.append("Signal Crossover Buy. Price: 2500. Qty: 20")
    events_rel.append("PnL: 300.0 (Win)")
for _ in range(6):
    events_rel.append("Signal Crossover Buy. Price: 2500. Qty: 20")
    events_rel.append("PnL: -300.0 (Loss)")

write_log("supertrend_vwap_strategy_RELIANCE.log", events_rel)

# 4. MCX Normal
# mcx_commodity_momentum_strategy_GOLD.log
# Signals: 5, Entries: 5.
# Wins: 3, Losses: 2.
events_gold = []
for _ in range(3):
    events_gold.append("Signal Detected: BUY. ADX: 30") # Counts as Entry if logic holds?
    # Logic: ("BUY" or "SELL") AND ("Signal" or "Crossover")
    # Yes.
    events_gold.append("PnL: 5000.0 (Win)")
for _ in range(2):
    events_gold.append("Signal Detected: SELL. ADX: 30")
    events_gold.append("PnL: -2000.0 (Loss)")

write_log("mcx_commodity_momentum_strategy_GOLD.log", events_gold)
