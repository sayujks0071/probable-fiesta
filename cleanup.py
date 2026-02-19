import os
import shutil

files_to_remove = [
    "openalgo/strategies/active_strategies.json",
    "openalgo/log/strategies/Momentum_INFY.log",
    "openalgo/log/strategies/MeanReversion_RELIANCE.log",
    "openalgo/strategies/state/INFY_state.json",
    "openalgo/strategies/state/RELIANCE_state.json",
]

dirs_to_remove = [
    "openalgo/strategies/state",
    "openalgo/log/strategies"
]

for f in files_to_remove:
    if os.path.exists(f):
        os.remove(f)
        print(f"Removed {f}")

# Only remove dirs if empty
for d in dirs_to_remove:
    if os.path.exists(d):
        try:
            os.rmdir(d)
            print(f"Removed directory {d}")
        except OSError:
            print(f"Directory {d} not empty, skipping")
