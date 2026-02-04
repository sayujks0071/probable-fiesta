#!/usr/bin/env python3
"""
Cost Optimization & Tax Efficiency Analyzer
-------------------------------------------
Analyzes trading logs to calculate realized transaction costs including:
- Brokerage (assumed discount model)
- STT (Securities Transaction Tax) / CTT
- Exchange Transaction Charges
- GST
- Stamp Duty
- SEBI Turnover Fees

Provides insights into "Net P&L" vs "Gross P&L" and efficiency ratios.
"""

import os
import sys
import re
import argparse
import logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("CostAnalyzer")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "strategies/logs"
ALT_LOG_DIR = BASE_DIR / "log/strategies"

class CostCalculator:
    """
    Calculator for Indian Stock Market Taxes & Charges (FY 2024-25 estimates).
    """
    def __init__(self, brokerage_per_order: float = 20.0):
        self.brokerage_per_order = brokerage_per_order

    def calculate_charges(self, trade: Dict) -> Dict[str, float]:
        """
        Calculate charges for a completed trade (Entry + Exit).

        Args:
            trade: Dict containing:
                - symbol: str
                - quantity: int (abs value)
                - buy_price: float
                - sell_price: float
                - product: 'MIS' (Intraday) or 'CNC' (Delivery) or 'NRML' (F&O)
                - segment: 'EQUITY', 'FUTURES', 'OPTIONS', 'COMMODITY'

        Returns:
            Dict breakdown of charges.
        """
        qty = trade.get('quantity', 0)
        buy_price = trade.get('buy_price', 0.0)
        sell_price = trade.get('sell_price', 0.0)
        segment = trade.get('segment', 'EQUITY') # Default to Equity
        product = trade.get('product', 'MIS') # Default to Intraday

        buy_turnover = qty * buy_price
        sell_turnover = qty * sell_price
        total_turnover = buy_turnover + sell_turnover

        # 1. Brokerage
        # Flat fee per executed order (1 Buy + 1 Sell = 2 orders)
        # Cap at 2.5% of trade value if low value? Usually flat 20.
        brokerage = self.brokerage_per_order * 2

        # 2. STT / CTT
        stt = 0.0
        if segment == 'COMMODITY':
            # CTT: 0.01% on Sell (Non-Agri Futures)
            stt = sell_turnover * 0.0001
        elif segment == 'OPTIONS':
            # Equity Options: 0.0625% on Sell (on Premium)
            stt = sell_turnover * 0.000625
        elif segment == 'FUTURES':
            # Equity Futures: 0.0125% on Sell
            stt = sell_turnover * 0.000125
        else: # EQUITY
            if product == 'CNC': # Delivery
                # 0.1% on Buy & Sell
                stt = total_turnover * 0.001
            else: # Intraday
                # 0.025% on Sell
                stt = sell_turnover * 0.00025

        # 3. Exchange Transaction Charges (NSE Estimates)
        exch_charge = 0.0
        if segment == 'COMMODITY':
            exch_charge = total_turnover * 0.000026 # MCX approx
        elif segment == 'OPTIONS':
            exch_charge = total_turnover * 0.00053 # NSE Options (on premium)
        elif segment == 'FUTURES':
            exch_charge = total_turnover * 0.00002 # NSE Futures
        else: # EQUITY
            exch_charge = total_turnover * 0.0000345 # NSE Equity

        # 4. SEBI Turnover Fees
        # ₹10 per crore = 0.0001%
        sebi_fees = total_turnover * 0.000001

        # 5. Stamp Duty
        # 0.003% on Buy side only (Intraday/F&O), 0.015% Delivery
        stamp_duty = 0.0
        if segment == 'EQUITY' and product == 'CNC':
            stamp_duty = buy_turnover * 0.00015
        else:
            stamp_duty = buy_turnover * 0.00003

        # 6. GST
        # 18% on (Brokerage + Exch Charges + SEBI Fees)
        # STT/Stamp Duty are exempt
        taxable_value = brokerage + exch_charge + sebi_fees
        gst = taxable_value * 0.18

        total_charges = brokerage + stt + exch_charge + sebi_fees + stamp_duty + gst

        return {
            'brokerage': brokerage,
            'stt': stt,
            'exch_charge': exch_charge,
            'sebi_fees': sebi_fees,
            'stamp_duty': stamp_duty,
            'gst': gst,
            'total': total_charges
        }

class LogParser:
    def __init__(self):
        self.trades = []

    def infer_segment_product(self, symbol: str) -> tuple[str, str]:
        """Infer Segment and Product from Symbol."""
        symbol = symbol.upper()

        if 'FUT' in symbol:
            if 'CRUDE' in symbol or 'GOLD' in symbol or 'SILVER' in symbol or 'COPPER' in symbol:
                return 'COMMODITY', 'NRML'
            return 'FUTURES', 'NRML'

        if 'CE' in symbol or 'PE' in symbol:
             return 'OPTIONS', 'NRML'

        if 'GOLD' in symbol or 'SILVER' in symbol: # MCX Mini/Bulldex
            return 'COMMODITY', 'NRML'

        # Default Equity Intraday
        return 'EQUITY', 'MIS'

    def parse_logs(self, log_dir: Path, days: int = 30):
        if not log_dir.exists():
            return

        logger.info(f"Scanning logs in {log_dir}...")

        # Regex Patterns (matching risk_manager.py format)
        # Entry: "Position registered: LONG 50 SBIN @ 500.00"
        entry_pattern = re.compile(r'Position registered:\s*(LONG|SHORT)\s*([-]?\d+)\s*(\S+)\s*@\s*([-\d.]+)', re.I)

        # Exit: "Position closed: SBIN @ 505.00, PnL: 250.00"
        exit_pattern = re.compile(r'Position closed:\s*(\S+)\s*@\s*([-\d.]+).*PnL:\s*([-\d.]+)', re.I)

        # Timestamp
        time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')

        cutoff_date = datetime.now().timestamp() - (days * 86400)

        for log_file in log_dir.glob("*.log"):
            # Check modification time
            if log_file.stat().st_mtime < cutoff_date:
                continue

            # Per-file state to match entry/exit
            # Need to handle FIFO or assume last entry matches next exit
            # For simplicity, we'll track open positions
            open_positions = defaultdict(list) # symbol -> list of {qty, price, time}

            with open(log_file, 'r', errors='ignore') as f:
                for line in f:
                    time_match = time_pattern.search(line)
                    if not time_match:
                        continue

                    try:
                        ts = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue

                    # Check Entry
                    entry_match = entry_pattern.search(line)
                    if entry_match:
                        side = entry_match.group(1)
                        qty = int(entry_match.group(2))
                        symbol = entry_match.group(3)
                        price = float(entry_match.group(4))

                        open_positions[symbol].append({
                            'side': side,
                            'qty': abs(qty),
                            'price': price,
                            'time': ts
                        })
                        continue

                    # Check Exit
                    exit_match = exit_pattern.search(line)
                    if exit_match:
                        symbol = exit_match.group(1)
                        exit_price = float(exit_match.group(2))
                        pnl = float(exit_match.group(3))

                        # Find matching entry (LIFO/FIFO - assuming LIFO for simplicity in log parsing context)
                        if open_positions[symbol]:
                            entry = open_positions[symbol].pop() # Get last entry

                            segment, product = self.infer_segment_product(symbol)

                            # Construct Trade Object
                            trade = {
                                'date': ts.strftime('%Y-%m-%d'),
                                'symbol': symbol,
                                'quantity': entry['qty'],
                                'buy_price': entry['price'] if entry['side'] == 'LONG' else exit_price,
                                'sell_price': exit_price if entry['side'] == 'LONG' else entry['price'],
                                'gross_pnl': pnl,
                                'segment': segment,
                                'product': product
                            }
                            self.trades.append(trade)

    def get_trades(self):
        return self.trades

def main():
    parser = argparse.ArgumentParser(description="Cost Optimization Analyzer")
    parser.add_argument("--days", type=int, default=30, help="Lookback period in days")
    parser.add_argument("--brokerage", type=float, default=20.0, help="Brokerage per order (flat)")
    args = parser.parse_args()

    # Parse Logs
    parser_obj = LogParser()
    parser_obj.parse_logs(LOG_DIR, args.days)
    parser_obj.parse_logs(ALT_LOG_DIR, args.days)

    trades = parser_obj.get_trades()
    if not trades:
        print("No completed trades found in logs.")
        return

    # Calculate Costs
    calculator = CostCalculator(brokerage_per_order=args.brokerage)

    total_gross_pnl = 0.0
    total_charges = 0.0
    total_turnover = 0.0

    charge_breakdown = defaultdict(float)

    print("\n" + "="*80)
    print(f"💰 COST EFFICIENCY REPORT (Last {args.days} Days)")
    print("="*80)
    print(f"{'Date':<12} {'Symbol':<15} {'Seg':<8} {'Qty':<6} {'Gr P&L':>10} {'Charges':>10} {'Net P&L':>10}")
    print("-" * 80)

    for trade in trades:
        costs = calculator.calculate_charges(trade)

        gross = trade['gross_pnl']
        total_charge = costs['total']
        net = gross - total_charge

        total_gross_pnl += gross
        total_charges += total_charge

        # Accumulate stats
        for k, v in costs.items():
            charge_breakdown[k] += v

        print(f"{trade['date']:<12} {trade['symbol']:<15} {trade['segment'][:7]:<8} {trade['quantity']:<6} {gross:>10.2f} {total_charge:>10.2f} {net:>10.2f}")

    net_pnl = total_gross_pnl - total_charges
    efficiency = (net_pnl / total_gross_pnl * 100) if total_gross_pnl > 0 else 0.0
    cost_drag = (total_charges / abs(total_gross_pnl) * 100) if total_gross_pnl != 0 else 0.0

    print("="*80)
    print(f"\n📊 SUMMARY")
    print(f"Total Trades Analyzed: {len(trades)}")
    print(f"Gross P&L:             ₹{total_gross_pnl:,.2f}")
    print(f"Total Charges:         ₹{total_charges:,.2f}")
    print(f"Net P&L:               ₹{net_pnl:,.2f}")
    print(f"Cost Drag:             {cost_drag:.2f}% of Gross Profit/Loss")

    print(f"\n💸 CHARGES BREAKDOWN")
    print(f"Brokerage:             ₹{charge_breakdown['brokerage']:,.2f}")
    print(f"STT/CTT:               ₹{charge_breakdown['stt']:,.2f}")
    print(f"Exchange Charges:      ₹{charge_breakdown['exch_charge']:,.2f}")
    print(f"GST (18%):             ₹{charge_breakdown['gst']:,.2f}")
    print(f"Stamp Duty & SEBI:     ₹{charge_breakdown['stamp_duty'] + charge_breakdown['sebi_fees']:,.2f}")

    # Optimization Suggestions
    print(f"\n💡 OPTIMIZATION TIPS")
    if charge_breakdown['brokerage'] / total_charges > 0.4:
        print("- Brokerage is high. Consider a zero-brokerage plan or reduce order frequency.")

    if charge_breakdown['stt'] / total_charges > 0.4:
        print("- STT is dominant. This is typical for Options/Delivery. Ensure high R:R per trade.")

    if cost_drag > 20:
        print(f"⚠️  CRITICAL: Costs are eating {cost_drag:.1f}% of your moves. Increase target size or reduce churn.")
    else:
        print("✅ Cost efficiency is acceptable.")

if __name__ == "__main__":
    main()
