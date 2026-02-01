#!/usr/bin/env python3
"""
Order Execution Analysis
------------------------
Analyzes strategy logs to evaluate execution quality:
- Slippage (Expected vs Fill Price)
- Order Failure Rate
- Fill Latency (Order Time vs Fill Time)
"""

import os
import sys
import re
import glob
import pandas as pd
import numpy as np
from datetime import datetime

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Paths
LOG_DIR = os.path.join(repo_root, 'openalgo/strategies/logs')
ALT_LOG_DIR = os.path.join(repo_root, 'openalgo/log/strategies')

class ExecutionAnalyzer:
    def __init__(self):
        self.orders = []

    def find_logs(self):
        logs = []
        for d in [LOG_DIR, ALT_LOG_DIR]:
            if os.path.exists(d):
                logs.extend(glob.glob(os.path.join(d, "*.log")))
        return logs

    def parse_logs(self):
        log_files = self.find_logs()
        print(f"Scanning {len(log_files)} log files for execution data...")

        # Regex patterns
        # Timestamp: 2024-05-01 10:00:00
        time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')

        # Order Entry: [ENTRY] Order Placed: {'status': 'success', 'data': {'order_id': '...', ...}}
        # Or sometimes just the dict: Order Placed: { ... }
        order_pattern = re.compile(r'\[ENTRY\] Order Placed: (.*)', re.I)

        # Position Update (Fill confirmation): Position Updated for SYMBOL: 1 @ 100.5
        pos_pattern = re.compile(r'Position Updated for ([A-Z0-9]+): ([-\d]+) @ ([-\d.]+)', re.I)

        # Slippage Protection Log
        slip_prot_pattern = re.compile(r'Slippage Protection Active. Converting MARKET to LIMIT @ ([-\d.]+)')

        for log_file in log_files:
            strategy_name = os.path.basename(log_file).replace('.log', '')

            # Temporary storage to match orders with fills
            pending_orders = [] # Stack or list of recent orders

            with open(log_file, 'r', errors='ignore') as f:
                for line in f:
                    time_match = time_pattern.search(line)
                    if not time_match:
                        continue

                    timestamp_str = time_match.group(1)
                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue

                    # Check for Order Placement
                    order_match = order_pattern.search(line)
                    if order_match:
                        # We found an order attempt
                        # Try to parse if it was a LIMIT order converted from MARKET (Slippage Prot)
                        # or just a standard order.
                        # Since we don't have the "Signal Price" easily in the log unless logged specifically,
                        # we can infer it if "Slippage Protection Active" was logged just before.

                        self.orders.append({
                            'strategy': strategy_name,
                            'timestamp': timestamp,
                            'type': 'ORDER_PLACED',
                            'details': order_match.group(1),
                            'filled': False,
                            'fill_price': None,
                            'slippage_prot': False
                        })
                        continue

                    # Check for Slippage Protection
                    if "Slippage Protection Active" in line:
                         # Mark the last added order or the next one?
                         # Usually logs happen sequentially.
                         # Logic: This log comes BEFORE the place_order call finishes and logs [ENTRY].
                         # So we store a flag to apply to the NEXT order found.
                         pass

                    # Check for Position Update (Fill)
                    pos_match = pos_pattern.search(line)
                    if pos_match:
                        symbol = pos_match.group(1)
                        qty = int(pos_match.group(2))
                        price = float(pos_match.group(3))

                        # Match with the most recent unfilled order for this strategy
                        # This is a heuristic matching
                        matched = False
                        for i in range(len(self.orders) - 1, -1, -1):
                            order = self.orders[i]
                            if order['strategy'] == strategy_name and not order['filled']:
                                # Allow match if timestamp is within reasonable window (e.g. 1 min)
                                delta = (timestamp - order['timestamp']).total_seconds()
                                if 0 <= delta <= 60:
                                    self.orders[i]['filled'] = True
                                    self.orders[i]['fill_price'] = price
                                    self.orders[i]['fill_time'] = timestamp
                                    self.orders[i]['fill_delay_sec'] = delta
                                    matched = True
                                    break

                        if not matched:
                            # Fill without identified order log (maybe restarted?)
                            pass

    def generate_report(self):
        if not self.orders:
            print("No order data found.")
            return

        df = pd.DataFrame(self.orders)

        print("\n" + "="*60)
        print("📊 EXECUTION QUALITY REPORT")
        print("="*60)

        total_orders = len(df)
        filled_orders = df[df['filled'] == True]

        fill_rate = (len(filled_orders) / total_orders) * 100 if total_orders > 0 else 0

        print(f"Total Orders:      {total_orders}")
        print(f"Filled Orders:     {len(filled_orders)}")
        print(f"Fill Rate:         {fill_rate:.1f}%")

        if not filled_orders.empty:
            avg_delay = filled_orders['fill_delay_sec'].mean()
            print(f"Avg Fill Latency:  {avg_delay:.2f} sec")

            # Slippage Analysis
            # Since we don't always know the exact "Signal Price", we can't calculate exact slippage
            # unless we parse the order dict for 'price' (if limit) or assume something.
            # But we can report the "Fill Price" distribution.
            pass

        # Failure Analysis
        failures = df[df['filled'] == False]
        if not failures.empty:
            print("\n⚠️  POTENTIAL ORDER FAILURES (No Fill Confirmation in 60s)")
            print(failures[['timestamp', 'strategy', 'details']].head().to_string())

if __name__ == "__main__":
    analyzer = ExecutionAnalyzer()
    analyzer.parse_logs()
    analyzer.generate_report()
