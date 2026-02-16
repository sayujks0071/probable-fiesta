#!/bin/bash
set -e

# Setup Environment
echo "Setting up environment..."
python3 tools/setup_env.py

# Export PYTHONPATH to include current directory
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Run Daily Prep
echo "Running Daily Prep..."
python3 openalgo/scripts/daily_prep.py

# Optional: Run Backtest
if [ "$1" == "--backtest" ]; then
    echo "Running Daily Backtest..."
    python3 openalgo/scripts/daily_backtest_leaderboard.py
fi
