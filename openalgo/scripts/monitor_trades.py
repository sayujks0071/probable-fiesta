#!/usr/bin/env python3
"""
Monitor Trade Logs
Scans strategy logs for today's trading activity.
"""
import os
import sys
import glob
import re
from datetime import datetime
from pathlib import Path

# Adjust paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LOG_DIR = REPO_ROOT / "strategies" / "logs"

def get_today_logs():
    """Find log files modified today."""
    if not LOG_DIR.exists():
        return []

    today = datetime.now().date()
    logs = []

    for log_file in LOG_DIR.glob("*.log"):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime).date()
        if mtime == today:
            logs.append(log_file)

    return logs

def parse_log_file(log_file):
    """Extract relevant events from a log file."""
    events = []
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                # Check for keywords
                timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else "Unknown Time"

                if "Order Placed" in line or "placed order" in line.lower():
                    events.append({'time': timestamp, 'type': 'ORDER', 'msg': line})
                elif "PnL" in line:
                    events.append({'time': timestamp, 'type': 'PNL', 'msg': line})
                elif "SIGNAL" in line:
                    events.append({'time': timestamp, 'type': 'SIGNAL', 'msg': line})
                elif "ERROR" in line or "Exception" in line:
                    events.append({'time': timestamp, 'type': 'ERROR', 'msg': line})
                elif "Risk Block" in line or "CIRCUIT BREAKER" in line:
                    events.append({'time': timestamp, 'type': 'RISK', 'msg': line})

    except Exception as e:
        print(f"Error reading {log_file.name}: {e}")

    return events

def main():
    print(f"--- Trade Monitor --- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Log Directory: {LOG_DIR}")

    logs = get_today_logs()

    if not logs:
        print("No logs found for today.")
        return

    all_events = []
    for log in logs:
        print(f"Scanning {log.name}...")
        events = parse_log_file(log)
        for e in events:
            e['source'] = log.name
        all_events.extend(events)

    # Sort by time
    all_events.sort(key=lambda x: x['time'])

    if not all_events:
        print("No significant events found today.")
        return

    print("\n" + "="*100)
    print(f"{'TIME':<20} | {'SOURCE':<25} | {'TYPE':<8} | {'MESSAGE'}")
    print("="*100)

    for e in all_events:
        # Truncate message if too long
        msg = e['msg']
        if len(msg) > 60:
            msg = msg[:57] + "..."

        print(f"{e['time']:<20} | {e['source'][:25]:<25} | {e['type']:<8} | {msg}")
    print("="*100)

if __name__ == "__main__":
    main()
