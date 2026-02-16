#!/usr/bin/env python3
"""
OpenAlgo Trade Monitor
======================
Monitors strategy logs for trade executions and calculates daily PnL.
"""

import os
import sys
import glob
import re
import time
import subprocess
from datetime import datetime

# Path Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(PROJECT_ROOT, "log", "strategies")

# Regex Patterns
# Look for patterns like: "Position Updated: 50 @ 19500" or "PnL: 500.0"
# Adapting to what I wrote in RiskManager/PositionManager logs.
# "Position closed: {symbol} @ {exit_price}, PnL: {pnl}"
# "Position registered: {side} {qty} {symbol} @ {entry_price}"

PNL_PATTERN = re.compile(r"PnL:\s*([-\d\.]+)")
ENTRY_PATTERN = re.compile(r"Position registered:\s*(\w+)\s*(-?\d+)\s*(\S+)\s*@\s*([\d\.]+)")
EXIT_PATTERN = re.compile(r"Position closed:\s*(\S+)\s*@\s*([\d\.]+).*PnL:\s*([-\d\.]+)")

def get_strategy_logs():
    """Get all .log files in the log directory."""
    if not os.path.exists(LOG_DIR):
        print(f"Log directory not found: {LOG_DIR}")
        return []
    return glob.glob(os.path.join(LOG_DIR, "*.log"))

def parse_log_file(filepath):
    """Parse a single log file for today's trades."""
    stats = {
        'trades': 0,
        'pnl': 0.0,
        'last_action': 'None',
        'active_position': 0
    }

    try:
        today_str = datetime.now().strftime("%Y-%m-%d")

        with open(filepath, 'r', errors='ignore') as f:
            for line in f:
                # Filter for today only (assuming log rotation or timestamp in line)
                # Timestamp format: 2023-10-27 09:15:00...
                if today_str not in line:
                    continue

                # Check for PnL
                pnl_match = PNL_PATTERN.search(line)
                if pnl_match:
                    pnl_val = float(pnl_match.group(1))
                    stats['pnl'] += pnl_val
                    stats['last_action'] = f"PnL {pnl_val}"

                # Check for Entry
                entry_match = ENTRY_PATTERN.search(line)
                if entry_match:
                    stats['trades'] += 1
                    side, qty, sym, price = entry_match.groups()
                    stats['last_action'] = f"Entry {side} {qty} @ {price}"
                    stats['active_position'] += int(qty) if side.upper() == 'LONG' else -int(qty) # Simplified

                # Check for Exit (PnL is usually in the same line, handled above)
                # But to track trades count if not using entry
                if "Position closed" in line:
                    # Double counting trades? Let's count 'round trips' or just 'executions'
                    pass

    except Exception as e:
        stats['last_action'] = f"Error: {str(e)}"

    return stats

def get_running_processes():
    """Get running strategy processes."""
    running = []
    try:
        cmd = ["pgrep", "-af", "strategies/scripts"]
        output = subprocess.check_output(cmd).decode("utf-8")
        for line in output.splitlines():
            if "monitor" in line: continue
            parts = line.split()
            pid = parts[0]
            cmd_str = " ".join(parts[1:])

            # Extract script name
            script_match = re.search(r'([\w_]+\.py)', cmd_str)
            script_name = script_match.group(1) if script_match else "unknown"

            running.append({'pid': pid, 'script': script_name})
    except:
        pass
    return running

def main():
    print(f"\n=== OpenAlgo Trade Monitor [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")
    print(f"Log Directory: {LOG_DIR}\n")

    # 1. Scan Logs
    log_files = get_strategy_logs()
    strategy_stats = {}

    for log_file in log_files:
        filename = os.path.basename(log_file)
        strategy_name = filename.replace(".log", "")
        stats = parse_log_file(log_file)
        if stats['trades'] > 0 or stats['pnl'] != 0:
            strategy_stats[strategy_name] = stats

    # 2. Check Running Processes
    running = get_running_processes()
    running_scripts = {p['script'] for p in running}

    # 3. Display Table
    print(f"{'STRATEGY':<30} {'STATUS':<10} {'TRADES':<8} {'DAILY PnL':<12} {'LAST ACTION'}")
    print("-" * 90)

    total_pnl = 0.0
    total_trades = 0

    # Combine logs and processes
    all_strategies = set(strategy_stats.keys()) | {p['script'].replace('.py', '') for p in running}

    for strategy in sorted(all_strategies):
        # Determine Status
        status = "STOPPED"
        # Check if any running script matches this strategy name (fuzzy match)
        for script in running_scripts:
            if strategy in script:
                status = "RUNNING"
                break

        stats = strategy_stats.get(strategy, {'trades': 0, 'pnl': 0.0, 'last_action': '-'})

        pnl_str = f"{stats['pnl']:+.2f}"
        color = ""
        if stats['pnl'] > 0: color = "\033[92m" # Green
        elif stats['pnl'] < 0: color = "\033[91m" # Red
        reset = "\033[0m"

        print(f"{strategy:<30} {status:<10} {stats['trades']:<8} {color}{pnl_str:<12}{reset} {stats['last_action']}")

        total_pnl += stats['pnl']
        total_trades += stats['trades']

    print("-" * 90)
    print(f"{'TOTAL':<41} {total_trades:<8} {total_pnl:+.2f}")
    print("\nNote: PnL is estimated from logs. Check broker for actuals.")

if __name__ == "__main__":
    main()
