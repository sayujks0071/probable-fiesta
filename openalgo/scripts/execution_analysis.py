#!/usr/bin/env python3
"""
Order Execution Analysis
------------------------
Analyzes strategy logs to evaluate execution quality:
- Fill Rate (Signals vs Executions)
- Execution Latency (Time from Signal to Position Update)
- Slippage (Estimated where possible)
"""

import os
import sys
import re
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
except ImportError:
    console = None

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Paths
LOG_DIR = os.path.join(repo_root, 'openalgo/strategies/logs')
ALT_LOG_DIR = os.path.join(repo_root, 'openalgo/log/strategies')

class ExecutionAnalyzer:
    def __init__(self, lookback_days=30):
        self.lookback_days = lookback_days
        self.orders = []
        self.signals = []
        self.fills = []

    def find_logs(self):
        logs = []
        for d in [LOG_DIR, ALT_LOG_DIR]:
            if os.path.exists(d):
                logs.extend([os.path.join(d, f) for f in os.listdir(d) if f.endswith('.log')])
        return logs

    def parse_logs(self):
        log_files = self.find_logs()
        if console:
            console.print(f"[bold blue]Scanning {len(log_files)} log files...[/bold blue]")
        else:
            print(f"Scanning {len(log_files)} log files...")

        # Regex patterns
        time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')

        # 1. Intent / Signal / Submission
        # Matches: "SmartOrder: Placing BUY 10 RELIANCE..."
        smart_order_pattern = re.compile(r'SmartOrder: Placing (BUY|SELL) (\d+) (.*) \(Urgency: (.*)\)', re.I)
        # Matches: "VWAP Crossover Buy. Price: 123.45..."
        vwap_signal_pattern = re.compile(r'(VWAP Crossover|Breakout) (Buy|Sell).*Price: ([\d\.]+)', re.I)
        # Matches: "BUY SIGNAL: Price=123.45..."
        generic_signal_pattern = re.compile(r'(BUY|SELL) SIGNAL: Price=([\d\.]+)', re.I)

        # 2. Execution / Fill
        # Matches: "Position Updated for RELIANCE: 10 @ 123.45"
        pos_update_pattern = re.compile(r'Position Updated for (.*?): ([-]?\d+) @ ([\d\.]+)', re.I)
        # Matches: "[ENTRY] Order Placed: ..."
        api_response_pattern = re.compile(r'\[ENTRY\] Order Placed:', re.I)

        for log_file in log_files:
            strategy_name = os.path.basename(log_file).replace('.log', '')
            strategy_name = re.sub(r'_\d{8}.*', '', strategy_name)

            with open(log_file, 'r', errors='ignore') as f:
                for line in f:
                    # Extract timestamp
                    time_match = time_pattern.search(line)
                    if not time_match:
                        continue

                    timestamp_str = time_match.group(1)
                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue

                    if (datetime.now() - timestamp).days > self.lookback_days:
                        continue

                    # Parse Intent (Signals)
                    signal_match = None
                    signal_price = None
                    action = None

                    # Check SmartOrder
                    m = smart_order_pattern.search(line)
                    if m:
                        action = m.group(1).upper()
                        # symbol = m.group(3)
                        self.signals.append({
                            'strategy': strategy_name,
                            'time': timestamp,
                            'type': 'SmartOrder',
                            'action': action,
                            'raw': line.strip()
                        })
                        continue

                    # Check Strategy Signals
                    m = vwap_signal_pattern.search(line)
                    if m:
                        action = m.group(2).upper() # "Buy" or "Sell"
                        signal_price = float(m.group(3))
                        self.signals.append({
                            'strategy': strategy_name,
                            'time': timestamp,
                            'type': 'Signal',
                            'action': action,
                            'price': signal_price,
                            'raw': line.strip()
                        })
                        continue

                    m = generic_signal_pattern.search(line)
                    if m:
                        action = m.group(1).upper()
                        signal_price = float(m.group(2))
                        self.signals.append({
                            'strategy': strategy_name,
                            'time': timestamp,
                            'type': 'Signal',
                            'action': action,
                            'price': signal_price,
                            'raw': line.strip()
                        })
                        continue

                    # Parse Execution (Fills)
                    m = pos_update_pattern.search(line)
                    if m:
                        symbol = m.group(1)
                        # qty = int(m.group(2)) # Note: Position is net pos, not trade qty, but change indicates trade
                        fill_price = float(m.group(3))

                        # We treat any position update with valid price as a fill event
                        if fill_price > 0:
                            self.fills.append({
                                'strategy': strategy_name,
                                'time': timestamp,
                                'symbol': symbol,
                                'price': fill_price,
                                'raw': line.strip()
                            })
                        continue

    def match_executions(self):
        """Match signals to fills based on time proximity."""
        # Sort both lists
        self.signals.sort(key=lambda x: x['time'])
        self.fills.sort(key=lambda x: x['time'])

        matched = []
        unfilled_signals = []

        # Simple greedy matching:
        # For each signal, look for the first fill within X seconds

        fill_indices_used = set()

        for sig in self.signals:
            best_fill_idx = -1
            min_latency = float('inf')

            # Look ahead in fills
            for i, fill in enumerate(self.fills):
                if i in fill_indices_used:
                    continue

                if fill['strategy'] != sig['strategy']:
                    continue

                # Check time diff
                delta = (fill['time'] - sig['time']).total_seconds()

                if delta < 0:
                    continue # Fill happened before signal (unlikely unless clock skew or parsing issue)

                if delta > 300: # Max 5 mins latency window
                    break # Fills are too far in future, stop looking for this signal

                # Found a potential fill
                if delta < min_latency:
                    min_latency = delta
                    best_fill_idx = i
                    break # Take the first one found close enough

            if best_fill_idx != -1:
                fill = self.fills[best_fill_idx]
                fill_indices_used.add(best_fill_idx)

                slippage = 0.0
                slippage_pct = 0.0
                if 'price' in sig and sig['price']:
                    if sig['action'] == 'BUY':
                        slippage = fill['price'] - sig['price']
                    elif sig['action'] == 'SELL':
                        slippage = sig['price'] - fill['price']

                    if sig['price'] > 0:
                        slippage_pct = (slippage / sig['price']) * 100

                matched.append({
                    'strategy': sig['strategy'],
                    'signal_time': sig['time'],
                    'fill_time': fill['time'],
                    'latency_sec': min_latency,
                    'signal_price': sig.get('price', 0),
                    'fill_price': fill['price'],
                    'slippage': slippage,
                    'slippage_pct': slippage_pct,
                    'action': sig['action']
                })
            else:
                unfilled_signals.append(sig)

        return matched, unfilled_signals

    def generate_report(self):
        matched, unfilled = self.match_executions()

        total_signals = len(matched) + len(unfilled)
        if total_signals == 0:
            msg = f"No execution data found in the last {self.lookback_days} days."
            if console:
                console.print(f"[yellow]{msg}[/yellow]")
            else:
                print(msg)
            return

        fill_rate = (len(matched) / total_signals) * 100 if total_signals > 0 else 0
        avg_latency = np.mean([m['latency_sec'] for m in matched]) if matched else 0

        # Slippage calculation (exclude where signal price was missing/zero)
        slippage_trades = [m for m in matched if m['signal_price'] > 0]
        avg_slippage_pct = np.mean([m['slippage_pct'] for m in slippage_trades]) if slippage_trades else 0

        # Header
        title = f"EXECUTION ANALYSIS REPORT (Last {self.lookback_days} Days)"
        if console:
            console.rule(f"[bold green]{title}")
        else:
            print(f"\n{title}\n{'='*len(title)}")

        # Summary
        summary = [
            ("Total Signals Detected", str(total_signals)),
            ("Total Fills Matched", str(len(matched))),
            ("Fill Rate", f"{fill_rate:.1f}%"),
            ("Avg Latency", f"{avg_latency:.2f} sec"),
            ("Avg Slippage", f"{avg_slippage_pct:.4f}%"),
        ]

        if console:
            table = Table(title="Overall Metrics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")
            for k, v in summary:
                table.add_row(k, v)
            console.print(table)
        else:
            print("\n--- Overall Metrics ---")
            for k, v in summary:
                print(f"{k:<25}: {v}")

        # Strategy Breakdown
        strat_stats = defaultdict(lambda: {'signals': 0, 'fills': 0, 'latency': [], 'slippage': []})

        for m in matched:
            s = m['strategy']
            strat_stats[s]['signals'] += 1
            strat_stats[s]['fills'] += 1
            strat_stats[s]['latency'].append(m['latency_sec'])
            if m['signal_price'] > 0:
                strat_stats[s]['slippage'].append(m['slippage_pct'])

        for u in unfilled:
            s = u['strategy']
            strat_stats[s]['signals'] += 1

        if console:
            table = Table(title="Strategy Breakdown")
            table.add_column("Strategy", style="white")
            table.add_column("Fill Rate", justify="right")
            table.add_column("Avg Latency (s)", justify="right")
            table.add_column("Avg Slippage %", justify="right")
        else:
            print("\n--- Strategy Breakdown ---")
            print(f"{'Strategy':<30} | {'Fill Rate':<10} | {'Latency(s)':<10} | {'Slippage %'}")

        for strat, stats in strat_stats.items():
            fr = (stats['fills'] / stats['signals'] * 100) if stats['signals'] > 0 else 0
            lat = np.mean(stats['latency']) if stats['latency'] else 0
            slip = np.mean(stats['slippage']) if stats['slippage'] else 0

            if console:
                table.add_row(
                    strat,
                    f"{fr:.1f}%",
                    f"{lat:.2f}",
                    f"{slip:.4f}"
                )
            else:
                print(f"{strat:<30} | {fr:>9.1f}% | {lat:>10.2f} | {slip:.4f}")

        if console:
            console.print(table)

def main():
    parser = argparse.ArgumentParser(description="Execution Analysis")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    args = parser.parse_args()

    analyzer = ExecutionAnalyzer(lookback_days=args.days)
    analyzer.parse_logs()
    analyzer.generate_report()

if __name__ == "__main__":
    main()
