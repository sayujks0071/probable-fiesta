#!/usr/bin/env python3
import os
import re
import glob
import logging
import argparse
from datetime import datetime
import pandas as pd
import numpy as np

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
# Log directories to scan
LOG_DIRS = [
    os.path.join(REPO_ROOT, 'log', 'strategies'),
    os.path.join(REPO_ROOT, 'strategies', 'logs')
]
STRATEGIES_DIR = os.path.join(REPO_ROOT, 'strategies', 'scripts')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

os.makedirs(REPORTS_DIR, exist_ok=True)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("EOD_Optimizer")

# Tunable Parameters Definition
# Mapping strategy names (partial) to their tunable parameters
TUNABLE_PARAMS = {
    'supertrend_vwap': ['threshold', 'stop_pct', 'adx_threshold'],
    'gap_fade': ['threshold', 'qty'],
    'ai_hybrid': ['rsi_lower', 'rsi_upper', 'stop_pct'],
    'orb': ['range_minutes', 'stop_loss_pct'],
    'mcx_momentum': ['threshold'],
    'default': ['threshold', 'stop_pct', 'stop_loss_pct', 'target_pct']
}

class StrategyOptimizer:
    def __init__(self):
        self.metrics = {}
        self.strategies_to_deploy = []
        self.improvements = []

    def parse_logs(self):
        log_files = []
        for d in LOG_DIRS:
            if os.path.exists(d):
                files = glob.glob(os.path.join(d, "*.log"))
                logger.info(f"Scanning {d}: Found {len(files)} logs.")
                log_files.extend(files)
            else:
                logger.warning(f"Log directory not found: {d}")

        if not log_files:
            logger.warning("No log files found in any directory.")
            return

        for log_file in log_files:
            filename = os.path.basename(log_file)
            # Assuming filename format: strategy_name_SYMBOL.log or just strategy.log
            # We need to extract strategy name and symbol
            # Heuristic: split by '_'
            # If ends with symbol like _NIFTY.log, take it.
            # Strategy names can have underscores too (e.g. gap_fade_strategy)

            name_part = filename.replace('.log', '')
            parts = name_part.split('_')

            # Common symbols
            known_symbols = ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS', 'INFY', 'CRUDEOIL', 'GOLD', 'SILVER', 'NATURALGAS', 'COPPER', 'ZINC', 'LEAD', 'ALUMINIUM']

            symbol = "UNKNOWN"
            strategy_name = name_part

            # Check if last part is a symbol
            if parts[-1].upper() in known_symbols or parts[-1].upper().endswith('FUT'):
                symbol = parts[-1]
                strategy_name = "_".join(parts[:-1])
            elif len(parts) > 1 and parts[-1].isupper(): # Guess it's a symbol if uppercase
                symbol = parts[-1]
                strategy_name = "_".join(parts[:-1])

            # Normalize strategy name (remove _strategy suffix if present, or keep it consistent)
            # The file is usually strategy_name.py
            # If log is gap_fade_strategy_NIFTY.log -> strategy: gap_fade_strategy
            # If file is gap_fade_strategy.py -> match

            with open(log_file, 'r') as f:
                lines = f.readlines()

            signals = 0
            entries = 0
            wins = 0
            losses = 0
            total_pnl = 0.0
            gross_win = 0.0
            gross_loss = 0.0
            errors = 0

            for line in lines:
                if "Error" in line or "Exception" in line:
                    errors += 1

                # Signal Detection
                # "Signal generated", "Buy Signal", "Sell Signal", "Gap found"
                if "Signal" in line or "Crossover" in line or "Gap found" in line or "Gap:" in line or "Opportunity" in line:
                    signals += 1

                # Entry Detection
                # "Order Placed", "Executing", "Buy", "Sell"
                # Avoid duplicates if multiple logs for same event
                if "Order Placed" in line or "Executing" in line or "entry executed" in line.lower():
                    entries += 1
                elif "BUY" in line or "SELL" in line:
                    # Sometimes simple BUY/SELL logs
                    if "Signal" not in line and "Crossover" not in line:
                         # potential entry if not just a signal log
                         pass

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        # Format: ... PnL: 150.0 ...
                        val_str = line.split("PnL:")[1].strip().split()[0]
                        val = float(val_str.replace(',', ''))
                        total_pnl += val
                        if val > 0:
                            wins += 1
                            gross_win += val
                        else:
                            losses += 1
                            gross_loss += abs(val)
                    except: pass
                elif "Trailing Stop Hit" in line:
                    # Fallback if PnL not logged explicitly
                    # Assume small win if trailing stop hit (usually profitable)
                    # Or check context. For now, count as win/loss based on nothing?
                    # Better to skip PnL calc but count as trade
                    pass

            # Refine signals/entries
            # If entries > signals (due to log verbosity), clamp
            if entries > signals: signals = entries

            # If wins+losses > entries, clamp
            total_trades = wins + losses
            if total_trades > entries: entries = total_trades
            if entries == 0 and total_trades > 0: entries = total_trades

            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (999 if wins > 0 else 0)
            rejection_rate = (1 - (entries / signals)) * 100 if signals > 0 else 0

            # Avg R:R
            avg_win = gross_win / wins if wins > 0 else 0
            avg_loss = gross_loss / losses if losses > 0 else 0
            rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            error_free_rate = 1.0
            if errors > 0:
                error_free_rate = max(0, 1 - (errors / (len(lines) if len(lines) > 0 else 1)))

            # Score Calculation
            # Prompt: Score = (Win Rate × 0.3) + (Profit Factor × 0.3) + (Sharpe × 0.2) + (Entry Rate × 0.1) + (Error-Free Rate × 0.1)
            # Sharpe proxy: use R:R capped at 3
            sharpe_proxy = min(rr_ratio, 3.0)

            # Normalize to 0-100 scale for comparable weighting
            # Win Rate: 0-100
            # Profit Factor: 0-3 -> 0-100 (x33) or 0-5 -> 0-100 (x20).
            # Existing script used min(pf, 10)*10. Let's stick to that.
            # Sharpe: 0-3 -> 0-100 (x33). Existing script used *20.
            # Entry Rate: 0-1 -> 0-100 (entries/signals * 100)
            # Error Rate: 0-1 -> 0-100 (error_free_rate * 100)

            # Adjusted to exactly match prompt weights (0.3, 0.3, 0.2, 0.1, 0.1) applied to normalized scores
            s_wr = win_rate
            s_pf = min(profit_factor, 10) * 10
            s_sh = sharpe_proxy * 20 # 2.0 -> 40, 3.0 -> 60. Maybe low?
            s_er = (entries/signals * 100) if signals > 0 else 0
            s_ef = error_free_rate * 100

            score = (s_wr * 0.3) + (s_pf * 0.3) + (s_sh * 0.2) + (s_er * 0.1) + (s_ef * 0.1)

            # Store metrics
            # Use symbol in key to differentiate same strategy on different symbols
            key = f"{strategy_name}::{symbol}"
            self.metrics[key] = {
                'strategy': strategy_name,
                'symbol': symbol,
                'signals': signals,
                'entries': entries,
                'wins': wins,
                'losses': losses,
                'wr': win_rate,
                'pf': profit_factor,
                'rr': rr_ratio,
                'rejection': rejection_rate,
                'errors': errors,
                'score': score
            }

    def optimize_strategies(self):
        # Group by strategy to apply changes once per file
        # But wait, different symbols might have different performance.
        # Strategy file is shared. We should optimize based on aggregate performance or worst case?
        # Or maybe average?
        # Let's aggregate metrics per strategy file.

        strategy_stats = {}
        for key, data in self.metrics.items():
            strat = data['strategy']
            if strat not in strategy_stats:
                strategy_stats[strat] = []
            strategy_stats[strat].append(data)

        for strategy, stats_list in strategy_stats.items():
            # Calculate aggregate metrics
            # Weighted average by signals? Or just simple average?
            # Simple average for now
            avg_rejection = np.mean([d['rejection'] for d in stats_list])
            avg_wr = np.mean([d['wr'] for d in stats_list]) if any(d['entries'] > 0 for d in stats_list) else 0
            avg_rr = np.mean([d['rr'] for d in stats_list]) if any(d['wins'] > 0 for d in stats_list) else 0

            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                # Try adding _strategy suffix
                filepath = os.path.join(STRATEGIES_DIR, f"{strategy}_strategy.py")
                if not os.path.exists(filepath):
                    logger.warning(f"Strategy file not found for {strategy}")
                    continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            modified = False
            changes = []

            # Determine tunable params for this strategy
            target_params = TUNABLE_PARAMS.get('default', [])
            # Check keys in TUNABLE_PARAMS
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_params = TUNABLE_PARAMS[key]
                    break

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if avg_rejection > 70:
                for param in ['threshold', 'gap_threshold']:
                    if param in target_params:
                        # Regex for self.param = X (Class attr)
                        match = re.search(fr"(self\.{param}\s*=\s*)(\d+\.?\d*)", content)
                        if match:
                            current_val = float(match.group(2))
                            # Reduce by 5% or 5 points
                            delta = 5 if current_val > 10 else 0.1
                            new_val = max(0, current_val - delta)
                            if float(current_val).is_integer() and new_val.is_integer():
                                 new_val = int(new_val)
                            else:
                                 new_val = round(new_val, 2)
                            new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                            changes.append(f"{param}: {current_val} -> {new_val} (Lowered due to Rejection {avg_rejection:.1f}%)")
                            modified = True
                        else:
                            # Regex for argparse default
                            match = re.search(fr"(parser\.add_argument\(['\"]--{param}['\"].*default=)(\d+\.?\d*)", content)
                            if match:
                                current_val = float(match.group(2))
                                delta = 5 if current_val > 10 else 0.1
                                new_val = max(0, current_val - delta)
                                if float(current_val).is_integer() and new_val.is_integer():
                                     new_val = int(new_val)
                                else:
                                     new_val = round(new_val, 2)
                                new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                                changes.append(f"{param}: {current_val} -> {new_val} (Lowered due to Rejection {avg_rejection:.1f}%)")
                                modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if avg_wr < 60 and avg_wr > 0:
                # Tighten RSI Lower (make it lower)
                if 'rsi_lower' in target_params:
                     match = re.search(r"(parser\.add_argument\(['\"]--rsi_lower['\"].*default=)(\d+\.?\d*)", content)
                     if match:
                        current_val = float(match.group(2))
                        new_val = max(10, current_val - 5)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"rsi_lower: {current_val} -> {new_val} (Tightened due to WR {avg_wr:.1f}%)")
                        modified = True

                # Tighten Threshold (make it higher)
                if 'threshold' in target_params and not modified: # Don't double adjust if handled by rejection
                     # Only tighten if rejection is NOT high (don't fight the previous rule)
                     if avg_rejection < 50:
                         match = re.search(r"(self\.threshold\s*=\s*)(\d+\.?\d*)", content)
                         if match:
                            current_val = float(match.group(2))
                            delta = 5 if current_val > 10 else 0.1
                            new_val = current_val + delta
                            if float(current_val).is_integer() and new_val.is_integer():
                                 new_val = int(new_val)
                            else:
                                 new_val = round(new_val, 2)
                            new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                            changes.append(f"threshold: {current_val} -> {new_val} (Tightened due to WR {avg_wr:.1f}%)")
                            modified = True

                # Tighten ADX (make it higher)
                if 'adx_threshold' in target_params:
                     match = re.search(r"(self\.adx_threshold\s*=\s*)(\d+\.?\d*)", content)
                     if match:
                        current_val = float(match.group(2))
                        new_val = current_val + 2
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"adx_threshold: {current_val} -> {new_val} (Tightened due to WR {avg_wr:.1f}%)")
                        modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif avg_wr > 80:
                if 'rsi_lower' in target_params:
                     match = re.search(r"(parser\.add_argument\(['\"]--rsi_lower['\"].*default=)(\d+\.?\d*)", content)
                     if match:
                        current_val = float(match.group(2))
                        new_val = min(40, current_val + 5)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"rsi_lower: {current_val} -> {new_val} (Relaxed due to WR {avg_wr:.1f}%)")
                        modified = True

                if 'threshold' in target_params:
                     match = re.search(r"(self\.threshold\s*=\s*)(\d+\.?\d*)", content)
                     if match:
                        current_val = float(match.group(2))
                        delta = 5 if current_val > 10 else 0.1
                        new_val = max(0, current_val - delta)
                        if float(current_val).is_integer() and new_val.is_integer():
                             new_val = int(new_val)
                        else:
                             new_val = round(new_val, 2)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"threshold: {current_val} -> {new_val} (Relaxed due to WR {avg_wr:.1f}%)")
                        modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop (reduce stop_pct)
            if avg_rr < 1.5 and avg_wr < 80: # If WR is super high, maybe low RR is fine (scalping)
                if 'stop_pct' in target_params:
                    # Check class attr
                    match = re.search(r"(self\.stop_pct\s*=\s*)(\d+\.?\d*)", content)
                    if match:
                        current_val = float(match.group(2))
                        new_val = max(0.5, current_val - 0.2)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val:.1f}")
                        changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {avg_rr:.2f})")
                        modified = True
                    else:
                        # Check argparse
                        match = re.search(r"(parser\.add_argument\(['\"]--stop_pct['\"].*default=)(\d+\.?\d*)", content)
                        if match:
                             current_val = float(match.group(2))
                             new_val = max(0.5, current_val - 0.2)
                             new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val:.1f}")
                             changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {avg_rr:.2f})")
                             modified = True

            if modified:
                # Add comment with date
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"
                # Insert after shebang or imports
                lines = new_content.split('\n')
                # Find best place to insert (after docstring or imports)
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('"""') and i > 0: # End of docstring
                        insert_idx = i + 1
                        break
                    if line.startswith('import '):
                        insert_idx = i
                        break

                if insert_idx == 0 and len(lines) > 1: insert_idx = 1 # After shebang

                lines.insert(insert_idx, comment)
                new_content = '\n'.join(lines)

                with open(filepath, 'w') as f:
                    f.write(new_content)

                self.improvements.append({
                    'strategy': strategy,
                    'changes': changes
                })
                logger.info(f"Updated {strategy}: {changes}")

    def generate_report(self):
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_file = os.path.join(REPORTS_DIR, f"eod_report_{date_str}.md")

        # Sort by score. Flatten metrics first?
        # Use metrics directly which is keyed by "Strategy::Symbol"
        sorted_strategies = sorted(self.metrics.items(), key=lambda x: x[1]['score'], reverse=True)

        # Select unique strategies for deployment (pick best symbol per strategy or just strategy name?)
        # Deployment script needs strategy name.
        # We will deploy distinct strategies that appear in top list.
        seen_strategies = set()
        self.strategies_to_deploy = []
        for key, m in sorted_strategies:
            strat = m['strategy']
            if strat not in seen_strategies:
                self.strategies_to_deploy.append(strat)
                seen_strategies.add(strat)
            if len(self.strategies_to_deploy) >= 5:
                break

        with open(report_file, 'w') as f:
            f.write(f"# 📊 END-OF-DAY REPORT - {date_str}\n\n")

            f.write("## 📈 TODAY'S PERFORMANCE SUMMARY:\n")
            f.write("| Strategy | Symbol | Signals | Entries | Wins | WR% | PF | R:R | Rej% | Score | Status |\n")
            f.write("|----------|--------|---------|---------|------|-----|----|-----|------|-------|--------|\n")
            for key, m in sorted_strategies:
                status = "✓" if m['score'] > 50 else "✗"
                f.write(f"| {m['strategy']} | {m['symbol']} | {m['signals']} | {m['entries']} | {m['wins']} | {m['wr']:.1f}% | {m['pf']:.1f} | {m['rr']:.2f} | {m['rejection']:.1f}% | {m['score']:.1f} | {status} |\n")

            f.write("\n## 🔧 INCREMENTAL IMPROVEMENTS APPLIED:\n")
            for item in self.improvements:
                f.write(f"### {item['strategy']}\n")
                for change in item['changes']:
                    f.write(f"- {change}\n")

            f.write("\n## 📊 STRATEGY RANKING (Top 5 for Tomorrow):\n")
            for i, name in enumerate(self.strategies_to_deploy):
                # Find score from metrics (first occurrence)
                score = next((m['score'] for k,m in sorted_strategies if m['strategy'] == name), 0)
                f.write(f"{i+1}. {name} - Score: {score:.1f} - Action: Start/Restart\n")

        print(f"Report generated: {report_file}")
        # with open(report_file, 'r') as f:
        #     print(f.read())

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")
            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/'\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                # Check for correct script filename (strategy.py or strategy_strategy.py)
                script_name = f"{strategy}.py"
                if not os.path.exists(os.path.join(STRATEGIES_DIR, script_name)):
                    script_name = f"{strategy}_strategy.py"
                    if not os.path.exists(os.path.join(STRATEGIES_DIR, script_name)):
                         logger.warning(f"Could not find script for {strategy}")
                         continue

                # Need to find a valid symbol for the strategy. Use the one from logs or default.
                # Find best symbol for this strategy from metrics
                best_symbol = "NIFTY"
                best_score = -1
                for k, m in self.metrics.items():
                    if m['strategy'] == strategy and m['score'] > best_score:
                        best_score = m['score']
                        best_symbol = m['symbol']

                f.write(f"nohup python3 openalgo/strategies/scripts/{script_name} --symbol {best_symbol} --api_key $OPENALGO_APIKEY > openalgo/strategies/logs/{strategy}_{best_symbol}.log 2>&1 &\n")

            f.write("\necho 'Deployment complete.'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
