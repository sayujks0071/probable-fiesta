#!/usr/bin/env python3
import os
import re
import sys
import glob
import argparse
from pathlib import Path

# Setup paths
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
strategies_log_dir = project_root / "openalgo" / "strategies" / "logs"

def parse_log_file(filepath):
    """Parse a single log file for trading performance."""
    pnl = 0.0
    wins = 0
    losses = 0

    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()

            for line in lines:
                # Look for PnL statements
                # Pattern: "PnL: <float>" or "Realized PnL: <float>"
                # Matches: "Closed Long. PnL: 150.0"
                match = re.search(r"PnL:\s*(-?\d+\.?\d*)", line)
                if match:
                    amount = float(match.group(1))
                    # Filter out Unrealized PnL if logged differently, but usually 'PnL:' implies realized in these scripts
                    # Some scripts log "Unrealized PnL:", need to avoid that.
                    if "Unrealized" in line:
                        continue

                    pnl += amount
                    if amount > 0:
                        wins += 1
                    elif amount < 0: # Count flat as neither or loss? Let's say loss of opportunity or ignore.
                        losses += 1

    except Exception as e:
        print(f"Error reading {filepath}: {e}")

    return {
        'filename': os.path.basename(filepath),
        'pnl': pnl,
        'trades': wins + losses,
        'wins': wins,
        'losses': losses
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze Strategy Logs")
    parser.add_argument("--file", help="Specific log file to analyze")
    args = parser.parse_args()

    files = []
    if args.file:
        files = [strategies_log_dir / args.file]
    else:
        files = list(strategies_log_dir.glob("*.log"))

    if not files:
        print(f"No log files found in {strategies_log_dir}")
        return

    print(f"{'STRATEGY LOG':<40} | {'TRADES':<8} | {'WIN RATE':<10} | {'TOTAL PnL':<15}")
    print("-" * 85)

    total_pnl = 0.0
    total_trades = 0

    for log_file in files:
        if not log_file.exists():
            continue

        stats = parse_log_file(log_file)

        win_rate = 0.0
        if stats['trades'] > 0:
            win_rate = (stats['wins'] / stats['trades']) * 100

        print(f"{stats['filename']:<40} | {stats['trades']:<8} | {win_rate:6.2f}%   | {stats['pnl']:15.2f}")

        total_pnl += stats['pnl']
        total_trades += stats['trades']

    print("-" * 85)
    print(f"{'TOTAL':<40} | {total_trades:<8} | {'-':<10} | {total_pnl:15.2f}")

if __name__ == "__main__":
    main()
