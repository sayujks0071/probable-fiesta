#!/usr/bin/env python3
"""
Cost Optimization & Tax Efficiency Analyzer
-------------------------------------------
Analyzes strategy logs to calculate Realized P&L and estimates transaction costs
(Brokerage, STT, Exchange Fees, GST, Stamp Duty) to provide Net P&L.
Helps in identifying excessive trading and optimizing costs.
"""

import os
import sys
import re
import argparse
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("CostAnalyzer")

from collections import defaultdict

try:
    import tabulate
except ImportError:
    tabulate = None

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "strategies/logs"
ALT_LOG_DIR = BASE_DIR / "log/strategies"

# Tax & Fee Constants (Estimates for Discount Brokers in India as of late 2024)
BROKERAGE_PER_ORDER = 20.0  # Flat rate per executed order
GST_RATE = 0.18             # 18% on Brokerage + Exchange Fees
SEBI_FEES = 0.000001        # ₹10 per crore
STAMP_DUTY_INTRADAY = 0.00003 # 0.003% (Buy only)
STAMP_DUTY_FUTURES = 0.00002  # 0.002% (Buy only)
STAMP_DUTY_OPTIONS = 0.00003  # 0.003% (Buy only)

class CostCalculator:
    @staticmethod
    def get_charges(symbol, qty, price, side, asset_type='EQUITY_INTRADAY', exchange='NSE'):
        """
        Calculate charges for a single trade leg.

        Args:
            symbol (str): Trading symbol
            qty (int): Quantity traded
            price (float): Trade price
            side (str): 'BUY' or 'SELL'
            asset_type (str): 'EQUITY_INTRADAY', 'EQUITY_DELIVERY', 'FUTURES', 'OPTIONS', 'COMMODITY'
            exchange (str): 'NSE' or 'MCX'

        Returns:
            dict: Breakdown of charges
        """
        turnover = price * abs(qty)
        charges = {
            'brokerage': 0.0,
            'stt': 0.0,
            'exchange_txn': 0.0,
            'sebi': 0.0,
            'stamp_duty': 0.0,
            'gst': 0.0,
            'total': 0.0
        }

        # 1. Brokerage (Flat 20 or 0.03%, whichever is lower - typical discount broker)
        # Using flat 20 for simplicity as most algo traders use flat plans
        charges['brokerage'] = min(BROKERAGE_PER_ORDER, turnover * 0.0003)
        # Actually most are Flat 20. Let's use Flat 20 per order.
        charges['brokerage'] = BROKERAGE_PER_ORDER

        # 2. STT / CTT
        if asset_type == 'EQUITY_INTRADAY':
            if side == 'SELL':
                charges['stt'] = turnover * 0.00025 # 0.025% on Sell
        elif asset_type == 'EQUITY_DELIVERY':
            charges['stt'] = turnover * 0.001 # 0.1% on Buy & Sell
        elif asset_type == 'FUTURES':
            if side == 'SELL':
                charges['stt'] = turnover * 0.0002 # 0.02% on Sell (Updated 2024)
        elif asset_type == 'OPTIONS':
            if side == 'SELL':
                charges['stt'] = turnover * 0.001 # 0.1% on Sell Premium (Updated 2024)
        elif asset_type == 'COMMODITY': # MCX Futures
            if side == 'SELL':
                charges['stt'] = turnover * 0.0001 # 0.01% CTT on Sell

        # 3. Exchange Transaction Charges
        if exchange == 'NSE':
            if asset_type == 'EQUITY_INTRADAY' or asset_type == 'EQUITY_DELIVERY':
                charges['exchange_txn'] = turnover * 0.0000325
            elif asset_type == 'FUTURES':
                charges['exchange_txn'] = turnover * 0.000019
            elif asset_type == 'OPTIONS':
                charges['exchange_txn'] = turnover * 0.0005
        elif exchange == 'MCX':
            charges['exchange_txn'] = turnover * 0.000026 # approx for futures

        # 4. SEBI Fees
        charges['sebi'] = turnover * SEBI_FEES

        # 5. Stamp Duty (Buy Only)
        if side == 'BUY':
            if asset_type == 'EQUITY_INTRADAY':
                charges['stamp_duty'] = turnover * STAMP_DUTY_INTRADAY
            elif asset_type == 'FUTURES' or asset_type == 'COMMODITY':
                charges['stamp_duty'] = turnover * STAMP_DUTY_FUTURES
            elif asset_type == 'OPTIONS':
                charges['stamp_duty'] = turnover * STAMP_DUTY_OPTIONS
            elif asset_type == 'EQUITY_DELIVERY':
                charges['stamp_duty'] = turnover * 0.00015 # 0.015%

        # 6. GST (18% on Brokerage + Exch + SEBI)
        # Note: SEBI fees are sometimes excluded from GST base depending on broker interpretation,
        # but strictly it's on service. Usually GST is on Brokerage + Exch Txn.
        charges['gst'] = (charges['brokerage'] + charges['exchange_txn']) * GST_RATE

        # Total
        charges['total'] = sum(charges.values())
        return charges

    @staticmethod
    def infer_asset_class(symbol):
        """Infer Asset Class and Exchange from Symbol."""
        symbol = symbol.upper()
        exchange = 'NSE'
        asset_type = 'EQUITY_INTRADAY' # Default

        # MCX Check
        mcx_commodities = ['GOLD', 'SILVER', 'CRUDE', 'COPPER', 'ZINC', 'LEAD', 'ALUMINI', 'NICKEL', 'NG', 'NATURALGAS', 'MENTHAOIL']
        is_mcx = any(symbol.startswith(c) for c in mcx_commodities)

        if is_mcx or 'MCX' in symbol:
            exchange = 'MCX'
            asset_type = 'COMMODITY'
        elif symbol.endswith('FUT') or 'FUT' in symbol:
            asset_type = 'FUTURES'
        elif 'CE' in symbol or 'PE' in symbol:
            asset_type = 'OPTIONS' # Simplistic check, might need refinement
        else:
            asset_type = 'EQUITY_INTRADAY' # Default to Intraday Equity

        return asset_type, exchange

class LogParser:
    def __init__(self, days=30):
        self.days = days
        self.trades = []

    def find_logs(self):
        logs = []
        for d in [LOG_DIR, ALT_LOG_DIR]:
            if d.exists():
                logs.extend(list(d.glob("*.log")))
        return logs

    def parse(self):
        log_files = self.find_logs()
        print(f"Scanning {len(log_files)} log files for trades in the last {self.days} days...")

        # Regex Patterns
        # 1. Position Update: "Position Updated for <SYM>: <POS> @ <AVG_PRICE>"
        pos_pattern = re.compile(r'Position Updated.*for\s+([A-Z0-9_-]+):\s*([-\d]+)\s*@\s*([-\d.]+)', re.I)

        # 2. PnL (Exit): "Closed.*PnL:\s*([-\d.]+)" or just "PnL:\s*([-\d.]+)"
        pnl_pattern = re.compile(r'PnL[:=]\s*([-\d.]+)', re.I)

        # 3. Timestamp: "2024-05-20 10:00:00"
        time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')

        for log_file in log_files:
            strategy_name = log_file.stem.split('_20')[0] # Remove timestamp suffix

            # State tracking per symbol
            # symbol -> { 'pos': int, 'entry_price': float, 'last_update': datetime }
            symbol_state = {}
            pending_pnl = None # Store PnL if it appears before Position Update

            try:
                with open(log_file, 'r', errors='ignore') as f:
                    for line in f:
                        # Extract Time
                        time_match = time_pattern.search(line)
                        if not time_match:
                            continue

                        try:
                            timestamp = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            continue

                        if (datetime.now() - timestamp).days > self.days:
                            continue

                        # Check for PnL (usually precedes an exit in trading_utils)
                        pnl_match = pnl_pattern.search(line)
                        if pnl_match:
                            pending_pnl = float(pnl_match.group(1))

                        # Check for Position Update
                        pos_match = pos_pattern.search(line)
                        if pos_match:
                            sym = pos_match.group(1)
                            new_pos = int(pos_match.group(2))
                            avg_price = float(pos_match.group(3))

                            if sym not in symbol_state:
                                symbol_state[sym] = {'pos': 0, 'entry_price': 0.0}

                            prev_pos = symbol_state[sym]['pos']

                            # Determine Trade details
                            qty_traded = new_pos - prev_pos

                            if qty_traded != 0:
                                side = 'BUY' if qty_traded > 0 else 'SELL'
                                abs_qty = abs(qty_traded)

                                # Infer Price
                                trade_price = avg_price # Default

                                # If closing position (partial or full)
                                is_exit = (prev_pos > 0 and new_pos < prev_pos) or (prev_pos < 0 and new_pos > prev_pos)
                                is_entry = not is_exit

                                # If it's an entry, the reported avg_price is the trade price
                                # If it's an exit, avg_price might be 0 (if fully closed) or weighted avg of remaining.
                                # We need a better price for Exit to calculate Turnover.
                                # If we have pending_pnl, we can try to back-calculate if needed,
                                # but using the Entry Price (from state) is a solid proxy for Turnover calculation
                                # because PnL is usually small relative to Notional.
                                if is_exit and trade_price == 0:
                                    trade_price = symbol_state[sym]['entry_price']

                                asset_type, exchange = CostCalculator.infer_asset_class(sym)

                                trade_record = {
                                    'strategy': strategy_name,
                                    'symbol': sym,
                                    'timestamp': timestamp,
                                    'side': side,
                                    'qty': abs_qty,
                                    'price': trade_price,
                                    'asset_type': asset_type,
                                    'exchange': exchange,
                                    'is_exit': is_exit,
                                    'pnl_realized': 0.0
                                }

                                if is_exit and pending_pnl is not None:
                                    trade_record['pnl_realized'] = pending_pnl
                                    pending_pnl = None # Consume it

                                self.trades.append(trade_record)

                                # Update State
                                symbol_state[sym]['pos'] = new_pos
                                symbol_state[sym]['entry_price'] = avg_price

            except Exception as e:
                pass # logging.error(f"Error parsing {log_file}: {e}")

    def calculate_costs(self):
        if not self.trades:
            print("No trades found.")
            return

        print("\n" + "="*80)
        print(f"💰 COST & TAX ANALYSIS (Last {self.days} Days)")
        print("="*80)

        total_gross_pnl = 0.0
        total_charges = 0.0
        total_net_pnl = 0.0

        breakdown_total = defaultdict(float)

        processed_trades = []

        for t in self.trades:
            # If price is 0 (exit w/o price), try to fix it
            if t['price'] <= 0:
                # Heuristic: use 1000 or find entry?
                # Better: Look for previous entry for this symbol
                # For now, let's skip or warn.
                # Actually, capturing entry price from state is better.
                # In the loop above, I set trade_price = avg_price.
                # For Exit, avg_price became 0 in PositionManager if pos=0.
                # So if new_pos=0, price is 0.
                # We need the previous entry price.
                # This logic needs to be in parse loop.
                pass

            # Recalculate cost with simple logic:
            # If price is 0, we can't calc turnover.
            # But we can assume Exit Price approx Entry Price.
            # Let's handle this in the report loop.

            price = t['price']
            if price == 0 and t['is_exit']:
                 # Try to find previous entry for this symbol
                 prev_entries = [x for x in processed_trades if x['symbol'] == t['symbol'] and not x['is_exit']]
                 if prev_entries:
                     price = prev_entries[-1]['price']

            if price <= 0:
                continue # Can't calc cost

            charges = CostCalculator.get_charges(
                t['symbol'], t['qty'], price, t['side'], t['asset_type'], t['exchange']
            )

            t_cost = charges['total']
            t_pnl = t.get('pnl_realized', 0.0)

            # PnL is only on Exits usually.
            if not t['is_exit']:
                t_pnl = 0.0

            total_gross_pnl += t_pnl
            total_charges += t_cost
            total_net_pnl += (t_pnl - t_cost) if t['is_exit'] else (-t_cost) # If entry, cost is loss

            # Aggregate charges
            for k, v in charges.items():
                if k != 'total':
                    breakdown_total[k] += v

            processed_trades.append({
                'Date': t['timestamp'].strftime('%Y-%m-%d %H:%M'),
                'Strategy': t['strategy'],
                'Symbol': t['symbol'],
                'Side': t['side'],
                'Qty': t['qty'],
                'Price': price,
                'Type': t['asset_type'],
                'Gross P&L': t_pnl if t['is_exit'] else 0.0,
                'Costs': t_cost,
                'Net P&L': (t_pnl - t_cost) if t['is_exit'] else -t_cost
            })

        # Summary
        df = pd.DataFrame(processed_trades)
        if df.empty:
            print("No valid trades to analyze.")
            return

        print(f"\n📈 OVERALL SUMMARY")
        print(f"Total Trades:      {len(df)}")
        print(f"Gross P&L:         ₹{total_gross_pnl:,.2f}")
        print(f"Total Charges:     \033[91m-₹{total_charges:,.2f}\033[0m")
        print(f"Net P&L:           \033[1m₹{total_gross_pnl - total_charges:,.2f}\033[0m")

        profit_impact = (total_charges / abs(total_gross_pnl)) * 100 if total_gross_pnl != 0 else 0
        print(f"Cost Impact:       {profit_impact:.1f}% of Gross P&L")

        print(f"\n💸 TAX BREAKDOWN")
        for k, v in breakdown_total.items():
            print(f"  {k.replace('_', ' ').title():<15} ₹{v:,.2f}")

        # Strategy Breakdown
        print(f"\n🏆 BY STRATEGY")
        strat_stats = df.groupby('Strategy')[['Gross P&L', 'Costs', 'Net P&L']].sum().sort_values('Net P&L', ascending=False)

        if tabulate:
            print(tabulate.tabulate(strat_stats, headers="keys", tablefmt="github", floatfmt=".2f"))
        else:
            print(strat_stats.to_string())

        # Recommendation
        if profit_impact > 20:
            print("\n⚠️  ADVISORY: High Cost Impact (>20%).")
            print("   Consider reducing trade frequency, switching to delivery, or checking for over-trading.")

def main():
    parser = argparse.ArgumentParser(description="Cost Analyzer")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    args = parser.parse_args()

    analyzer = LogParser(days=args.days)
    analyzer.parse()
    analyzer.calculate_costs()

if __name__ == "__main__":
    main()
