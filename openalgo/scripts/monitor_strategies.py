#!/usr/bin/env python3
"""
Monitor running strategies and their logs.
"""
import os
import sys
import time
import subprocess
import re
import json
import glob
from datetime import datetime

# Adjust paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR) # openalgo/
LOG_DIR = os.path.join(REPO_ROOT, "log", "strategies")
STATE_DIR = os.path.join(REPO_ROOT, "strategies", "state")

def get_risk_state(script_name, symbol):
    """Try to find and read the risk state file."""
    if not symbol or symbol == "UNKNOWN":
        return {}

    # Map script names to likely strategy prefixes
    # This is a heuristic based on how strategies name themselves in RiskManager
    prefix_map = {
        "supertrend_vwap_strategy.py": "SuperTrendVWAP",
        "mcx_global_arbitrage_strategy.py": "MCXArbitrage",
        "sentiment_reversal_strategy.py": "SentimentReversal",
        "delta_neutral_iron_condor_nifty.py": "IronCondor",
        "gap_fade_strategy.py": "GapFade",
    }

    # Try specific name first
    prefix = prefix_map.get(script_name, "")
    candidates = []
    if prefix:
        candidates.append(os.path.join(STATE_DIR, f"{prefix}_{symbol}_risk_state.json"))

    # Generic fallback: {symbol}_risk_state.json
    candidates.append(os.path.join(STATE_DIR, f"{symbol}_risk_state.json"))

    # Search for any file ending in {symbol}_risk_state.json
    candidates.extend(glob.glob(os.path.join(STATE_DIR, f"*{symbol}_risk_state.json")))

    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except:
                pass
    return {}

def get_running_strategies():
    """Find running strategy processes."""
    strategies = []
    try:
        # pgrep -af returns PID and command line
        cmd = ["pgrep", "-af", "strategies/scripts"]
        output = subprocess.check_output(cmd).decode("utf-8")

        for line in output.splitlines():
            if "monitor_strategies.py" in line: continue

            parts = line.split()
            pid = parts[0]
            cmdline = " ".join(parts[1:])

            # Redact API Keys and Secrets
            cmdline = re.sub(r'--api_key\s+[^\s]+', '--api_key [REDACTED]', cmdline)
            cmdline = re.sub(r'api_key=[^\s]+', 'api_key=[REDACTED]', cmdline)
            cmdline = re.sub(r'--secret\s+[^\s]+', '--secret [REDACTED]', cmdline)

            # Extract script name
            script_match = re.search(r'([\w_]+\.py)', cmdline)
            script_name = script_match.group(1) if script_match else "unknown"

            # Extract symbol
            symbol_match = re.search(r'--symbol\s+(\w+)', cmdline)
            symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"

            # Extract Logfile
            log_match = re.search(r'--logfile\s+([^\s]+)', cmdline)
            logfile = log_match.group(1) if log_match else None

            strategies.append({
                "pid": pid,
                "script": script_name,
                "symbol": symbol,
                "logfile": logfile,
                "cmd": cmdline
            })

    except subprocess.CalledProcessError:
        pass

    return strategies

def tail_log(logfile, lines=5):
    if not logfile or not os.path.exists(logfile):
        return ["Log file not found"]
    try:
        cmd = ["tail", "-n", str(lines), logfile]
        return subprocess.check_output(cmd).decode("utf-8").splitlines()
    except:
        return ["Error reading log"]

def main():
    print(f"--- OpenAlgo Strategy Monitor --- {datetime.now()}")
    strategies = get_running_strategies()

    if not strategies:
        print("No strategies running.")
        return

    print(f"{'PID':<8} {'SYMBOL':<15} {'STRATEGY':<30} {'PnL':<12} {'TRADES':<8} {'STATUS':<10} {'LOG FILE'}")
    print("-" * 120)

    for s in strategies:
        log_display = s['logfile'] if s['logfile'] else "N/A"

        # Fetch Risk State
        risk_state = get_risk_state(s['script'], s['symbol'])
        daily_pnl = risk_state.get('daily_pnl', 'N/A')
        if daily_pnl != 'N/A': daily_pnl = f"{float(daily_pnl):.2f}"

        daily_trades = risk_state.get('daily_trades', 'N/A')
        cb = risk_state.get('circuit_breaker', False)
        status = "HALTED" if cb else "RUNNING"

        print(f"{s['pid']:<8} {s['symbol']:<15} {s['script']:<30} {daily_pnl:<12} {str(daily_trades):<8} {status:<10} {log_display}")

        # If we have a logfile, show last line
        if s['logfile']:
            logs = tail_log(s['logfile'], 1)
            if logs:
                print(f"  Last Log: {logs[0]}")
        print("")

if __name__ == "__main__":
    main()
