#!/usr/bin/env python3
"""
Monitor running strategies and their logs.
"""
import os
import sys
import time
import subprocess
import re
from datetime import datetime

# Adjust paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR) # openalgo/
LOG_DIR = os.path.join(REPO_ROOT, "log", "strategies")

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

            # If logfile not explicitly passed, guess it based on script/symbol (best effort)
            if not logfile:
                 # Standard convention: openalgo/log/strategies/{script_name_no_py}_{symbol}.log or similar?
                 # gap_fade_strategy.py logs to gap_fade.log
                 # Let's just rely on what we found or check default paths
                 pass

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

    # Check Instruments Master
    instruments_path = os.path.join(REPO_ROOT, "data", "instruments.csv")
    if not os.path.exists(instruments_path):
        print(f"\033[93m[WARNING] Instruments master missing: {instruments_path}. Symbol resolution may fail.\033[0m")

    strategies = get_running_strategies()

    if not strategies:
        print("No strategies running.")
        return

    print(f"{'PID':<8} {'SYMBOL':<10} {'STRATEGY':<30} {'STATUS':<10} {'LOG FILE'}")
    print("-" * 90)

    for s in strategies:
        status = "RUNNING"
        log_display = s['logfile'] if s['logfile'] else "N/A"

        # Check for Stale Logs
        if s['logfile'] and os.path.exists(s['logfile']):
            mtime = os.path.getmtime(s['logfile'])
            age = time.time() - mtime
            if age > 300: # 5 mins
                status = "STALE"
                # ANSI Red for Stale
                status = f"\033[91m{status}\033[0m"

        print(f"{s['pid']:<8} {s['symbol']:<10} {s['script']:<30} {status:<10} {log_display}")

        # If we have a logfile, show last line
        if s['logfile']:
            logs = tail_log(s['logfile'], 1)
            if logs:
                print(f"  Last Log: {logs[0]}")
        print("")

if __name__ == "__main__":
    main()
