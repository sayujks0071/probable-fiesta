#!/usr/bin/env python3
import os
import re
import glob
import logging
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
from collections import defaultdict

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(REPO_ROOT, 'log', 'strategies')
STRATEGIES_DIR = os.path.join(REPO_ROOT, 'strategies', 'scripts')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("EOD_Optimizer")

# Tunable Parameters Definition
TUNABLE_PARAMS = {
    'supertrend_vwap': ['threshold', 'stop_pct', 'quantity'],
    'ai_hybrid': ['rsi_lower', 'rsi_upper', 'stop_pct', 'quantity'],
    'orb': ['range_minutes', 'stop_loss_pct', 'quantity'],
    'default': ['threshold', 'stop_pct', 'stop_loss_pct', 'target_pct', 'quantity']
}

class StrategyOptimizer:
    def __init__(self):
        # Key: strategy_name, Value: dict of aggregated metrics
        self.metrics = defaultdict(lambda: {
            'signals': 0, 'entries': 0, 'wins': 0, 'losses': 0,
            'gross_win': 0.0, 'gross_loss': 0.0, 'errors': 0,
            'rejection_reasons': defaultdict(int),
            'hourly_stats': defaultdict(lambda: {'signals': 0, 'entries': 0, 'pnl': 0.0}),
            'symbols': set(),
            'log_lines_count': 0
        })
        self.strategies_to_deploy = []
        self.improvements = []
        self.insights = []
        self.issues = []

    def parse_logs(self):
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        logger.info(f"Found {len(log_files)} log files in {LOG_DIR}.")

        for log_file in log_files:
            filename = os.path.basename(log_file)
            parts = filename.replace('.log', '').split('_')
            # Heuristic: last part is symbol if uppercase and length <= 10
            if parts[-1].isupper() and len(parts[-1]) <= 10:
                symbol = parts[-1]
                strategy_name = "_".join(parts[:-1])
            else:
                symbol = "UNKNOWN"
                strategy_name = "_".join(parts)

            with open(log_file, 'r') as f:
                lines = f.readlines()

            m = self.metrics[strategy_name]
            m['symbols'].add(symbol)
            m['log_lines_count'] += len(lines)

            for line in lines:
                # Timestamp extraction
                timestamp_match = re.search(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                current_hour = None
                if timestamp_match:
                    try:
                        dt = datetime.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S")
                        current_hour = dt.hour
                    except ValueError:
                        pass

                if "Error" in line or "Exception" in line:
                    m['errors'] += 1
                    self.issues.append(f"{strategy_name} ({symbol}): {line.strip()}")

                # Signal Detection
                if "Signal" in line or "Crossover" in line:
                    m['signals'] += 1
                    if current_hour is not None:
                        m['hourly_stats'][current_hour]['signals'] += 1

                # Rejection Detection
                if "Reject" in line or "Skipping" in line or "Filter" in line:
                    parts_line = line.split(" - ")
                    if len(parts_line) >= 4:
                        reason = parts_line[3].strip()
                        m['rejection_reasons'][reason] += 1
                    else:
                        m['rejection_reasons']["Unknown Rejection"] += 1

                # Entry Detection
                if "Entry" in line and ("BUY" in line or "SELL" in line):
                    m['entries'] += 1
                    if current_hour is not None:
                        m['hourly_stats'][current_hour]['entries'] += 1

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        val_str = line.split("PnL:")[1].strip().split()[0]
                        val = float(val_str)
                        if current_hour is not None:
                            m['hourly_stats'][current_hour]['pnl'] += val

                        if val > 0:
                            m['wins'] += 1
                            m['gross_win'] += val
                        else:
                            m['losses'] += 1
                            m['gross_loss'] += abs(val)
                    except: pass
                elif "Trailing Stop Hit" in line:
                    pass

        # Finalize metrics calculation
        for strategy, m in self.metrics.items():
            total_trades = m['wins'] + m['losses']
            m['wr'] = (m['wins'] / total_trades * 100) if total_trades > 0 else 0
            m['pf'] = (m['gross_win'] / m['gross_loss']) if m['gross_loss'] > 0 else (999 if m['wins'] > 0 else 0)
            m['rejection'] = (1 - (m['entries'] / m['signals'])) * 100 if m['signals'] > 0 else 0

            avg_win = m['gross_win'] / m['wins'] if m['wins'] > 0 else 0
            avg_loss = m['gross_loss'] / m['losses'] if m['losses'] > 0 else 0
            m['rr'] = avg_win / avg_loss if avg_loss > 0 else 0

            error_free_rate = 1.0
            if m['errors'] > 0:
                error_free_rate = max(0, 1 - (m['errors'] / (m['log_lines_count'] if m['log_lines_count'] > 0 else 1)))

            # Score Calculation
            pf_score = min(m['pf'], 5.0) * 20
            sharpe_score = min(m['rr'], 3.0) * 33.3
            entry_rate_score = (m['entries'] / m['signals'] * 100) if m['signals'] > 0 else 0

            m['score'] = (m['wr'] * 0.3) + (pf_score * 0.3) + (sharpe_score * 0.2) + (entry_rate_score * 0.1) + (error_free_rate * 100 * 0.1)

    def optimize_strategies(self):
        for strategy, data in self.metrics.items():
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                logger.warning(f"Strategy file not found: {filepath}")
                continue

            with open(filepath, 'r') as f:
                content = f.read()

            current_content = content
            modified = False
            changes = []

            target_params = TUNABLE_PARAMS.get('default', [])
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_params = TUNABLE_PARAMS[key]
                    break

            # Helper to safely replace in current_content
            def safe_replace(pattern, replacement_func, content, change_desc):
                match = re.search(pattern, content)
                if match:
                    new_val = replacement_func(match)
                    if new_val is not None:
                         # Construct replacement string
                         # Expecting groups: 1=prefix (e.g. "self.threshold = "), 2=value
                         new_str = f"{match.group(1)}{new_val}"
                         # Only replace if different
                         if new_str != match.group(0):
                             # Need to escape for regex replacement or simple string replace?
                             # String replace is safer if match is unique enough
                             return content.replace(match.group(0), new_str), True
                return content, False

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                if 'threshold' in target_params:
                    match = re.search(r"(self\.threshold\s*=\s*)(\d+)", current_content)
                    if match:
                        current_val = int(match.group(2))
                        new_val = max(0, current_val - 5)
                        new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        if new_content_tmp != current_content:
                            current_content = new_content_tmp
                            changes.append(f"threshold: {current_val} -> {new_val} (Lowered due to Rejection {data['rejection']:.1f}%)")
                            modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60 and data['entries'] > 0:
                # Tighten RSI Lower
                if 'rsi_lower' in target_params:
                     match = re.search(r"(parser\.add_argument\('--rsi_lower'.*default=)(\d+\.?\d*)", current_content)
                     if match:
                        current_val = float(match.group(2))
                        new_val = max(10, current_val - 5)
                        new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        if new_content_tmp != current_content:
                            current_content = new_content_tmp
                            changes.append(f"rsi_lower: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                            modified = True
                     # Check self.rsi_lower
                     elif 'self.rsi_lower' in current_content:
                        match = re.search(r"(self\.rsi_lower\s*=\s*)(\d+\.?\d*)", current_content)
                        if match:
                             current_val = float(match.group(2))
                             new_val = max(10, current_val - 5)
                             new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                             if new_content_tmp != current_content:
                                current_content = new_content_tmp
                                changes.append(f"rsi_lower: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                                modified = True

                # Tighten Threshold (only if not already modified by step 1)
                # Here we are increasing it, step 1 decreases it. So they conflict.
                # Since steps are sequential, we should check if we just lowered it.
                # If Rejection > 70 AND WR < 60, we have a dilemma.
                # Rejection says "Lower threshold to get more entries". WR says "Tighten to get better entries".
                # Usually WR > Rejection priority. But let's follow the sequence.
                # If we already modified, maybe skip?
                # For simplicity, we apply both if conditions met, effectively +0 or net change.
                if 'threshold' in target_params:
                     match = re.search(r"(self\.threshold\s*=\s*)(\d+)", current_content)
                     if match:
                        current_val = int(match.group(2))
                        new_val = current_val + 5
                        new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        if new_content_tmp != current_content:
                            current_content = new_content_tmp
                            changes.append(f"threshold: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                            modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                if 'rsi_lower' in target_params:
                     match = re.search(r"(parser\.add_argument\('--rsi_lower'.*default=)(\d+\.?\d*)", current_content)
                     if match:
                        current_val = float(match.group(2))
                        new_val = min(40, current_val + 5)
                        new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        if new_content_tmp != current_content:
                            current_content = new_content_tmp
                            changes.append(f"rsi_lower: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True
                     elif 'self.rsi_lower' in current_content:
                        match = re.search(r"(self\.rsi_lower\s*=\s*)(\d+\.?\d*)", current_content)
                        if match:
                             current_val = float(match.group(2))
                             new_val = min(40, current_val + 5)
                             new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                             if new_content_tmp != current_content:
                                current_content = new_content_tmp
                                changes.append(f"rsi_lower: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                                modified = True

                if 'threshold' in target_params:
                     match = re.search(r"(self\.threshold\s*=\s*)(\d+)", current_content)
                     if match:
                        current_val = int(match.group(2))
                        new_val = max(0, current_val - 5)
                        new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        if new_content_tmp != current_content:
                            current_content = new_content_tmp
                            changes.append(f"threshold: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop
            if data['rr'] < 1.5 and data['wr'] < 80 and data['wins'] > 0:
                if 'stop_pct' in target_params:
                    match = re.search(r"(self\.stop_pct\s*=\s*)(\d+\.?\d*)", current_content)
                    if match:
                        current_val = float(match.group(2))
                        new_val = max(0.5, current_val - 0.2)
                        new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val:.1f}")
                        if new_content_tmp != current_content:
                            current_content = new_content_tmp
                            changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {data['rr']:.2f})")
                            modified = True
                    else:
                        match = re.search(r"(parser\.add_argument\('--stop_pct'.*default=)(\d+\.?\d*)", current_content)
                        if match:
                             current_val = float(match.group(2))
                             new_val = max(0.5, current_val - 0.2)
                             new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val:.1f}")
                             if new_content_tmp != current_content:
                                current_content = new_content_tmp
                                changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {data['rr']:.2f})")
                                modified = True

            # 5. Position Sizing
            if data['wr'] < 40 and data['entries'] > 0:
                if 'quantity' in target_params:
                    match = re.search(r"(parser\.add_argument\('--quantity'.*default=)(\d+)", current_content)
                    if match:
                        current_val = int(match.group(2))
                        new_val = max(1, int(current_val * 0.8))
                        if new_val < current_val:
                            new_content_tmp = current_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                            if new_content_tmp != current_content:
                                current_content = new_content_tmp
                                changes.append(f"quantity: {current_val} -> {new_val} (Reduced due to Low WR {data['wr']:.1f}%)")
                                modified = True

            # 6. Time Filter Insights
            for hour, stats in data['hourly_stats'].items():
                if stats['entries'] >= 2 and stats['pnl'] < 0:
                     self.insights.append(f"{strategy}: Hour {hour} has negative PnL ({stats['pnl']}). Consider avoiding.")

            if modified:
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"
                lines = current_content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('"""') and i > 0:
                        insert_idx = i + 1
                        break
                    if line.startswith('import '):
                        insert_idx = i
                        break

                if insert_idx == 0 and len(lines) > 1: insert_idx = 1

                lines.insert(insert_idx, comment)
                current_content = '\n'.join(lines)

                with open(filepath, 'w') as f:
                    f.write(current_content)

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
            if not self.improvements:
                f.write("No changes applied.\n")
            for item in self.improvements:
                f.write(f"### {item['strategy']}\n")
                for change in item['changes']:
                    f.write(f"- {change}\n")

            f.write("\n## 📊 STRATEGY RANKING (Top 5 for Tomorrow):\n")
            for i, name in enumerate(self.strategies_to_deploy):
                score = self.metrics[name]['score']
                f.write(f"{i+1}. {name} - Score: {score:.1f} - Action: Start/Restart\n")

            f.write("\n## 🚀 DEPLOYMENT PLAN:\n")
            f.write("- Stop: All running strategies\n")
            f.write(f"- Start: {', '.join(self.strategies_to_deploy)}\n")

            f.write("\n## ⚠️ ISSUES FOUND:\n")
            if not self.issues:
                f.write("No critical issues found.\n")
            for issue in self.issues:
                f.write(f"- {issue}\n")

            f.write("\n## 💡 INSIGHTS FOR TOMORROW:\n")
            if not self.insights:
                f.write("No specific insights.\n")
            for insight in self.insights:
                f.write(f"- {insight}\n")

            f.write("\n## 📉 REJECTION ANALYSIS:\n")
            for name, m in sorted_strategies:
                if m['rejection_reasons']:
                    f.write(f"### {name}\n")
                    for reason, count in m['rejection_reasons'].items():
                        f.write(f"- {reason}: {count}\n")

            f.write("\n## 🕒 TIME OF DAY PERFORMANCE:\n")
            for name, m in sorted_strategies:
                if m['hourly_stats']:
                    f.write(f"### {name}\n")
                    f.write("| Hour | Signals | Entries | PnL |\n")
                    f.write("|------|---------|---------|-----|\n")
                    for hour in sorted(m['hourly_stats'].keys()):
                        stats = m['hourly_stats'][hour]
                        f.write(f"| {hour:02d} | {stats['signals']} | {stats['entries']} | {stats['pnl']:.1f} |\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")
            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/' || true\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                # Iterate over all symbols used for this strategy
                symbols = self.metrics.get(strategy, {}).get('symbols', [])
                if not symbols:
                    # Fallback if no symbols found (maybe strategy never ran but still in ranking?)
                    # But ranking comes from metrics, so symbols must exist.
                    # Unless strategy was in previous deployment but no logs today?
                    # The current logic only deploys strategies with logs today.
                    # This is acceptable for "Optimization" (only optimize what ran).
                    continue

                for symbol in symbols:
                    f.write(f"nohup python3 openalgo/strategies/scripts/{strategy}.py --symbol {symbol} --api_key $OPENALGO_APIKEY > openalgo/log/strategies/{strategy}_{symbol}.log 2>&1 &\n")

            f.write("\necho 'Deployment complete.'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
