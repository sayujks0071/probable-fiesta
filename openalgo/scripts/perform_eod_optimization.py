#!/usr/bin/env python3
import os
import re
import glob
import logging
import argparse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR) # openalgo/
LOG_DIR = os.path.join(REPO_ROOT, 'log', 'strategies')
STRATEGIES_DIR = os.path.join(REPO_ROOT, 'strategies', 'scripts')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

os.makedirs(REPORTS_DIR, exist_ok=True)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("EOD_Optimizer")

# Tunable Parameters Definition
# Mapping strategy names (partial) to their tunable parameters
TUNABLE_PARAMS = {
    'supertrend_vwap': {
        'threshold': 'threshold',
        'stop_pct': 'stop_pct',
        'adx_threshold': 'adx_threshold'
    },
    'ai_hybrid': {
        'rsi_lower': 'rsi_lower',
        'rsi_upper': 'rsi_upper',
        'stop_pct': 'stop_pct'
    },
    'mcx_commodity': {
        'adx_threshold': 'adx_threshold',
        'stop_pct': 'risk_per_trade', # Mapping concept if names differ
        'min_atr': 'min_atr'
    }
}

class StrategyOptimizer:
    def __init__(self):
        self.metrics = {}
        self.strategies_to_deploy = []
        self.improvements = []

    def parse_logs(self):
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        logger.info(f"Found {len(log_files)} log files.")

        for log_file in log_files:
            filename = os.path.basename(log_file)
            # Assuming filename format: strategy_name_SYMBOL.log
            # But sometimes symbols have underscores (e.g. CRUDE_OIL).
            # Better to take everything after last underscore as symbol?
            # Or assume strategy names don't have uppercase?
            # Common pattern: strategy_name_SYMBOL.log

            name_part = filename.replace('.log', '')
            parts = name_part.split('_')

            # Heuristic: Symbol is usually the last part, uppercase
            symbol = parts[-1]
            strategy_name = "_".join(parts[:-1])

            # Refined heuristic: if multiple uppercase parts at end, join them?
            # E.g. strategy_NIFTY_50.log -> symbol NIFTY_50
            # For now, simple split is okay for standard symbols.

            with open(log_file, 'r') as f:
                lines = f.readlines()

            signals = 0
            entries = 0
            wins = 0
            losses = 0
            gross_win = 0.0
            gross_loss = 0.0
            errors = 0
            rejection_reasons = {}

            # Time of Day Analysis (Simple)
            entry_times = []

            for line in lines:
                if "Error" in line or "Exception" in line:
                    errors += 1

                # Signal Detection
                if "Signal detected" in line or "Signal:" in line:
                    signals += 1

                # Rejection Reason
                if "Signal Rejected" in line:
                    # Extract reason
                    if "Signal Rejected: " in line:
                        reason = line.split("Signal Rejected: ")[1].strip()
                        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

                # Entry Detection
                if "Order Executed" in line and ("BUY" in line or "SELL" in line):
                    entries += 1
                    try:
                        timestamp_str = line.split(" - ")[0]
                        # Try parsing timestamp
                        # Format in mock: 2025-02-01 09:15:00,000
                        ts = timestamp_str.split(",")[0]
                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                        entry_times.append(dt)
                    except: pass

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        val_str = line.split("PnL:")[1].strip().split()[0]
                        val = float(val_str)
                        if val > 0:
                            wins += 1
                            gross_win += val
                        else:
                            losses += 1
                            gross_loss += abs(val)
                    except: pass

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if wins > 0 else 0.0)
            rejection_rate = (1 - (entries / signals)) * 100 if signals > 0 else 0.0

            # Avg R:R
            avg_win = gross_win / wins if wins > 0 else 0
            avg_loss = gross_loss / losses if losses > 0 else 0
            rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

            error_free_rate = 1.0
            if len(lines) > 0:
                error_free_rate = max(0, 1.0 - (errors / len(lines)))

            # Score Calculation
            # Score = (Win Rate × 0.3) + (Profit Factor × 0.3) + (Sharpe × 0.2) + (Entry Rate × 0.1) + (Error-Free Rate × 0.1)
            # Sharpe proxy: min(RR, 3)
            sharpe_proxy = min(rr_ratio, 3.0)

            # Normalize Profit Factor for score (cap at 5)
            pf_score = min(profit_factor, 5.0) / 5.0 * 100

            # Entry Rate (Entries / Signals)
            entry_rate = (entries / signals * 100) if signals > 0 else 0

            score = (win_rate * 0.3) + (pf_score * 0.3) + (sharpe_proxy * 33.3 * 0.2) + (entry_rate * 0.1) + (error_free_rate * 100 * 0.1)

            self.metrics[strategy_name] = {
                'symbol': symbol,
                'signals': signals,
                'entries': entries,
                'wins': wins,
                'losses': losses,
                'wr': win_rate,
                'pf': profit_factor,
                'rr': rr_ratio,
                'rejection': rejection_rate,
                'rejection_reasons': rejection_reasons,
                'errors': errors,
                'score': score
            }

    def update_parameter_in_content(self, content, param_name, current_val, new_val):
        """
        Helper to find and replace parameter value in content.
        Supports:
        1. self.param = val
        2. parser.add_argument(..., default=val)
        3. 'param': val (dict)
        """
        modified_content = content
        change_made = False

        # 1. self.param = val (Class attribute)
        # Regex: self.param_name = number
        pattern1 = fr"(self\.{param_name}\s*=\s*)(\d+(\.\d+)?)"
        match1 = re.search(pattern1, content)
        if match1:
            old_val_str = match1.group(2)
            # Replace
            new_val_str = f"{new_val}" if isinstance(new_val, int) else f"{new_val:.2f}"
            modified_content = modified_content.replace(match1.group(0), f"{match1.group(1)}{new_val_str}")
            return modified_content, True

        # 2. parser.add_argument(..., default=val) (Argparse)
        # Regex: parser.add_argument('--param_name', ... default=number)
        # Note: arg name might use hyphens instead of underscores
        arg_name = param_name.replace('_', '-') # Try hyphen version first for arg
        pattern2 = fr"(parser\.add_argument\s*\(['\"]--{param_name}['\"].*?default=)(\d+(\.\d+)?)"
        match2 = re.search(pattern2, content, re.DOTALL)
        if match2:
            old_val_str = match2.group(2)
            new_val_str = f"{new_val}" if isinstance(new_val, int) else f"{new_val:.2f}"
            modified_content = modified_content.replace(match2.group(0), f"{match2.group(1)}{new_val_str}")
            return modified_content, True

        # 3. 'param': val (Dict key)
        # Regex: 'param_name': number,
        pattern3 = fr"(['\"]{param_name}['\"]\s*:\s*)(\d+(\.\d+)?)"
        match3 = re.search(pattern3, content)
        if match3:
            old_val_str = match3.group(2)
            new_val_str = f"{new_val}" if isinstance(new_val, int) else f"{new_val:.2f}"
            modified_content = modified_content.replace(match3.group(0), f"{match3.group(1)}{new_val_str}")
            return modified_content, True

        return content, False

    def get_current_param_value(self, content, param_name):
        """Extract current value."""
        # 1. Class attr
        match = re.search(fr"self\.{param_name}\s*=\s*(\d+(\.\d+)?)", content)
        if match: return float(match.group(1))

        # 2. Argparse
        match = re.search(fr"parser\.add_argument\s*\(['\"]--{param_name}['\"].*?default=(\d+(\.\d+)?)", content, re.DOTALL)
        if match: return float(match.group(1))

        # 3. Dict
        match = re.search(fr"['\"]{param_name}['\"]\s*:\s*(\d+(\.\d+)?)", content)
        if match: return float(match.group(1))

        return None

    def optimize_strategies(self):
        for strategy, data in self.metrics.items():
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                # Try finding file with similar name (e.g. ignoring suffix)
                # But for now assume exact match or close enough
                logger.warning(f"Strategy file not found: {filepath}")
                continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            modified = False
            changes = []

            # Determine tunable params mapping
            # Find best match in TUNABLE_PARAMS
            target_map = {}
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_map = TUNABLE_PARAMS[key]
                    break

            # Default fallback if not found
            if not target_map:
                target_map = {'threshold': 'threshold', 'stop_pct': 'stop_pct'}

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                param_key = 'threshold'
                if param_key in target_map:
                    real_param_name = target_map[param_key]
                    current_val = self.get_current_param_value(content, real_param_name)
                    if current_val is not None:
                        # Assuming threshold is integer-like or significant
                        # If it's small (like 0.5), maybe it's not a threshold?
                        # Heuristic: if > 10, reduce by 5. If < 1, reduce by 0.05
                        if current_val > 10:
                            new_val = int(current_val - 5)
                            new_val = max(0, new_val)
                        else:
                            new_val = current_val - 0.05
                            new_val = max(0.01, new_val)

                        new_content, changed = self.update_parameter_in_content(new_content, real_param_name, current_val, new_val)
                        if changed:
                            changes.append(f"{real_param_name}: {current_val} -> {new_val} (Lowered due to Rejection {data['rejection']:.1f}%)")
                            modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                # Tighten RSI Lower (make it lower) if exists
                if 'rsi_lower' in target_map:
                    real_param_name = target_map['rsi_lower']
                    current_val = self.get_current_param_value(content, real_param_name)
                    if current_val is not None:
                        new_val = max(10, current_val - 5)
                        new_content, changed = self.update_parameter_in_content(new_content, real_param_name, current_val, new_val)
                        if changed:
                            changes.append(f"{real_param_name}: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                            modified = True

                # Or Increase Threshold
                elif 'threshold' in target_map and not modified:
                    real_param_name = target_map['threshold']
                    current_val = self.get_current_param_value(content, real_param_name)
                    if current_val is not None:
                         if current_val > 10:
                            new_val = int(current_val + 5)
                         else:
                            new_val = current_val + 0.05
                         new_content, changed = self.update_parameter_in_content(new_content, real_param_name, current_val, new_val)
                         if changed:
                             changes.append(f"{real_param_name}: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                             modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                if 'rsi_lower' in target_map:
                    real_param_name = target_map['rsi_lower']
                    current_val = self.get_current_param_value(content, real_param_name)
                    if current_val is not None:
                        new_val = min(45, current_val + 5)
                        new_content, changed = self.update_parameter_in_content(new_content, real_param_name, current_val, new_val)
                        if changed:
                            changes.append(f"{real_param_name}: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

                elif 'threshold' in target_map:
                    real_param_name = target_map['threshold']
                    current_val = self.get_current_param_value(content, real_param_name)
                    if current_val is not None:
                        if current_val > 10:
                            new_val = int(max(0, current_val - 5))
                        else:
                            new_val = max(0.01, current_val - 0.05)
                        new_content, changed = self.update_parameter_in_content(new_content, real_param_name, current_val, new_val)
                        if changed:
                            changes.append(f"{real_param_name}: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop
            if data['rr'] < 1.5 and data['wr'] < 85: # If WR is super high, low RR is acceptable
                if 'stop_pct' in target_map:
                    real_param_name = target_map['stop_pct']
                    current_val = self.get_current_param_value(content, real_param_name)
                    if current_val is not None:
                        # Reduce by 10%
                        if current_val > 1.0:
                            new_val = max(0.5, current_val * 0.9)
                        else:
                            new_val = max(0.005, current_val * 0.9)

                        # Round based on magnitude
                        if new_val < 0.1:
                            new_val = round(new_val, 4)
                        else:
                            new_val = round(new_val, 2)

                        new_content, changed = self.update_parameter_in_content(new_content, real_param_name, current_val, new_val)
                        if changed:
                            changes.append(f"{real_param_name}: {current_val} -> {new_val} (Tightened due to R:R {data['rr']:.2f})")
                            modified = True

            if modified:
                # Add comment with date
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"

                # Insert logic: After docstring
                lines = new_content.split('\n')
                insert_idx = 0
                docstring_open = False
                for i, line in enumerate(lines):
                    if '"""' in line or "'''" in line:
                        if docstring_open:
                            insert_idx = i + 1
                            break
                        docstring_open = True
                    if i > 5 and not docstring_open: # Fallback if no docstring
                        insert_idx = 1
                        break

                if insert_idx == 0: insert_idx = 1

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

        sorted_strategies = sorted(self.metrics.items(), key=lambda x: x[1]['score'], reverse=True)
        self.strategies_to_deploy = [s[0] for s in sorted_strategies[:5]]

        with open(report_file, 'w') as f:
            f.write(f"# 📊 END-OF-DAY REPORT - {date_str}\n\n")

            f.write("## 📈 TODAY'S PERFORMANCE SUMMARY:\n")
            f.write("| Strategy | Signals | Entries | Wins | WR% | PF | R:R | Rej% | Score | Status |\n")
            f.write("|----------|---------|---------|------|-----|----|-----|------|-------|--------|\n")
            for name, m in sorted_strategies:
                status = "✓" if m['score'] > 50 else "✗"
                f.write(f"| {name} | {m['signals']} | {m['entries']} | {m['wins']} | {m['wr']:.1f}% | {m['pf']:.1f} | {m['rr']:.2f} | {m['rejection']:.1f}% | {m['score']:.1f} | {status} |\n")

            f.write("\n## 🔧 INCREMENTAL IMPROVEMENTS APPLIED:\n")
            if self.improvements:
                for item in self.improvements:
                    f.write(f"### {item['strategy']}\n")
                    for change in item['changes']:
                        f.write(f"- {change}\n")
            else:
                f.write("No improvements required.\n")

            f.write("\n## 📊 STRATEGY RANKING (Top 5 for Tomorrow):\n")
            for i, name in enumerate(self.strategies_to_deploy):
                score = self.metrics[name]['score']
                f.write(f"{i+1}. {name} - Score: {score:.1f} - Action: Start/Restart\n")

            f.write("\n## 🚀 DEPLOYMENT PLAN:\n")
            f.write("- Stop: All running strategies\n")
            f.write("- Start: Top 5 strategies listed above\n")

            f.write("\n## ⚠️ ISSUES FOUND:\n")
            issues_found = False
            for name, m in self.metrics.items():
                if m['errors'] > 0:
                    f.write(f"- {name}: {m['errors']} Errors detected.\n")
                    issues_found = True
            if not issues_found:
                f.write("- No critical errors found.\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")

            f.write("# Environment Setup\n")
            f.write("export PYTHONPATH=$PYTHONPATH:$(pwd)\n")
            f.write("export OPENALGO_HOST='http://127.0.0.1:5001' # Default Kite\n")
            f.write("# Ensure API Key is set in environment before running this script\n\n")

            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/' || true\n\n")
            f.write("sleep 2\n")

            f.write("echo 'Starting optimized strategies...'\n")
            port_map = {0: 5001, 1: 5002} # Kite, Dhan

            for i, strategy in enumerate(self.strategies_to_deploy):
                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')
                port = port_map.get(i % 2, 5001) # Load balance

                f.write(f"echo 'Starting {strategy} on port {port}...'\n")
                f.write(f"nohup python3 openalgo/strategies/scripts/{strategy}.py --symbol {symbol} --port {port} --api_key $OPENALGO_APIKEY > openalgo/log/strategies/{strategy}_{symbol}.log 2>&1 &\n")

            f.write("\necho 'Deployment complete. verifying processes...'\n")
            f.write("sleep 2\n")
            f.write("pgrep -af 'python3 openalgo/strategies/scripts/'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
