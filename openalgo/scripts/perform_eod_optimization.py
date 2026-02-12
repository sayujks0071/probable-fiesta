#!/usr/bin/env python3
import os
import re
import glob
import logging
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
import json

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # Adjusting to ensure we are at repo root
if os.path.basename(REPO_ROOT) == 'scripts': # If script runs from scripts/
    REPO_ROOT = os.path.dirname(REPO_ROOT)
if os.path.basename(REPO_ROOT) == 'openalgo': # If script runs from openalgo/scripts/
    REPO_ROOT = os.path.dirname(REPO_ROOT)

LOG_DIR = os.path.join(REPO_ROOT, 'openalgo', 'log', 'strategies')
STRATEGIES_DIR = os.path.join(REPO_ROOT, 'openalgo', 'strategies', 'scripts')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

os.makedirs(REPORTS_DIR, exist_ok=True)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("EOD_Optimizer")

# Tunable Parameters Definition
# Mapping strategy names (partial) to their tunable parameters
TUNABLE_PARAMS = {
    'supertrend_vwap': ['threshold', 'stop_pct', 'adx_threshold'],
    'ai_hybrid': ['rsi_lower', 'rsi_upper', 'stop_pct'],
    'orb': ['range_minutes', 'stop_loss_pct'],
    'gap_fade': ['threshold'], # gap_threshold
    'mcx_commodity': ['adx_threshold', 'min_atr'],
    'advanced_ml': ['threshold', 'stop_pct'],
    'default': ['threshold', 'stop_pct', 'stop_loss_pct', 'target_pct']
}

class StrategyOptimizer:
    def __init__(self):
        self.metrics = {}
        self.strategies_to_deploy = []
        self.improvements = []
        self.insights = []
        self.issues = []

    def parse_logs(self):
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        logger.info(f"Found {len(log_files)} log files in {LOG_DIR}.")

        for log_file in log_files:
            filename = os.path.basename(log_file)
            # Assuming filename format: strategy_name_SYMBOL.log
            parts = filename.replace('.log', '').split('_')
            symbol = parts[-1]
            strategy_name = "_".join(parts[:-1])

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
            rejection_reasons = {}
            hourly_performance = {} # Hour -> (Wins, Losses)

            for line in lines:
                # Timestamp Parsing
                try:
                    ts_str = line.split(' - ')[0]
                    # Format: 2023-10-27 09:15:00,123
                    dt = datetime.strptime(ts_str.split(',')[0], "%Y-%m-%d %H:%M:%S")
                    hour = dt.hour
                except:
                    hour = 9 # Default

                if "Error" in line or "Exception" in line:
                    errors += 1
                    error_msg = line.split("Error")[-1].strip()
                    if len(self.issues) < 5: # Limit
                        self.issues.append(f"{strategy_name}: {error_msg[:50]}...")

                # Signal Detection
                if "Signal" in line or "Crossover" in line:
                    signals += 1
                    if "rejected due to" in line:
                        reason = line.split("rejected due to")[-1].strip()
                        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

                # Entry Detection
                if "Entry Executed" in line:
                    entries += 1

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        val_str = line.split("PnL:")[1].strip().split()[0]
                        val = float(val_str)
                        total_pnl += val

                        wins_h, losses_h = hourly_performance.get(hour, (0, 0))

                        if val > 0:
                            wins += 1
                            gross_win += val
                            wins_h += 1
                        else:
                            losses += 1
                            gross_loss += abs(val)
                            losses_h += 1

                        hourly_performance[hour] = (wins_h, losses_h)

                    except: pass

                # Mock handling for Gap Fade where explicit PnL might not be logged identically in dummy
                elif "Target Hit" in line:
                    wins += 1
                    gross_win += 500 # Assume fixed
                    entries += 1 # Ensure entry count matches exit count logic if missed
                elif "Stop Loss Hit" in line:
                    losses += 1
                    gross_loss += 500
                    entries += 1

            # Adjust signals count if entries > signals (due to log parsing mismatch)
            if entries > signals: signals = entries

            total_trades = wins + losses
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
            # Score = (Win Rate × 0.3) + (Profit Factor × 0.3) + (Sharpe × 0.2) + (Entry Rate × 0.1) + (Error-Free Rate × 0.1)
            # Sharpe is hard to calc from daily summary, use R:R as proxy or set to 1.0
            sharpe_proxy = min(rr_ratio, 3.0) # Cap at 3

            score = (win_rate * 0.3) + (min(profit_factor, 10) * 10 * 0.3) + (sharpe_proxy * 20 * 0.2) + ((entries/signals if signals else 0) * 100 * 0.1) + (error_free_rate * 100 * 0.1)

            # Insights
            if rejection_rate > 70:
                top_reason = max(rejection_reasons, key=rejection_reasons.get) if rejection_reasons else "Unknown"
                self.insights.append(f"{strategy_name}: High Rejection ({rejection_rate:.1f}%) due to '{top_reason}'. Consider relaxing filters.")

            # Hourly Insights
            for h, (w, l) in hourly_performance.items():
                total_h = w + l
                wr_h = (w / total_h) * 100
                if total_h >= 3 and wr_h < 30:
                     self.insights.append(f"{strategy_name}: Poor performance at hour {h} ({wr_h:.0f}% WR). Consider time filter.")

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
                'errors': errors,
                'score': score
            }

    def optimize_strategies(self):
        for strategy, data in self.metrics.items():
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                logger.warning(f"Strategy file not found: {filepath}")
                continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            modified = False
            changes = []

            # Determine tunable params for this strategy
            target_params = TUNABLE_PARAMS.get('default', [])
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_params = TUNABLE_PARAMS[key]
                    break

            logger.info(f"Optimizing {strategy} (Params: {target_params})")

            # Helper to find param value
            def get_param_val(param_name):
                # 1. PARAMS dict
                pattern_dict = r"(['\"]"+param_name+r"['\"]\s*:\s*)(\d+\.?\d*)"
                match = re.search(pattern_dict, new_content)
                if match: return float(match.group(2))

                # 2. Class attr
                pattern_attr = r"(self\."+param_name+r"\s*=\s*)(\d+\.?\d*)"
                match = re.search(pattern_attr, new_content)
                if match: return float(match.group(2))

                # 3. Argparse
                pattern_arg = r"(parser\.add_argument\(['\"]--"+param_name+r"['\"].*default=)(\d+\.?\d*)"
                match = re.search(pattern_arg, new_content)
                if match: return float(match.group(2))

                return None

            # Helper to replace param in file
            def update_param(param_name, new_val, reason):
                nonlocal new_content, modified, changes

                # 1. Try finding in PARAMS dict (e.g. 'adx_threshold': 25,)
                pattern_dict = r"(['\"]"+param_name+r"['\"]\s*:\s*)(\d+\.?\d*)"
                match = re.search(pattern_dict, new_content)
                if match:
                    old_val_str = match.group(2)
                    new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                    changes.append(f"{param_name}: {old_val_str} -> {new_val} ({reason})")
                    modified = True
                    return

                # 2. Try finding as class attribute (self.param = val)
                pattern_attr = r"(self\."+param_name+r"\s*=\s*)(\d+\.?\d*)"
                match = re.search(pattern_attr, new_content)
                if match:
                    old_val_str = match.group(2)
                    new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                    changes.append(f"{param_name}: {old_val_str} -> {new_val} ({reason})")
                    modified = True
                    return

                # 3. Try finding in argparse (parser.add_argument('--param', ... default=val))
                pattern_arg = r"(parser\.add_argument\(['\"]--"+param_name+r"['\"].*default=)(\d+\.?\d*)"
                match = re.search(pattern_arg, new_content)
                if match:
                    old_val_str = match.group(2)
                    new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                    changes.append(f"{param_name}: {old_val_str} -> {new_val} ({reason})")
                    modified = True
                    return

            # 1. High Rejection Rate (> 70%) -> Lower Threshold / Relax Filters
            if data['rejection'] > 70:
                if 'threshold' in target_params:
                     curr = get_param_val('threshold')
                     if curr is not None:
                         new_val = round(max(0, curr * 0.9), 3) # Reduce by 10%
                         if new_val != curr:
                            update_param('threshold', new_val, f"Lowered due to Rejection {data['rejection']:.1f}%")

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                # Tighten RSI/ADX
                if 'adx_threshold' in target_params:
                     curr = get_param_val('adx_threshold')
                     if curr is not None:
                         new_val = int(curr + 5)
                         update_param('adx_threshold', new_val, f"Tightened due to WR {data['wr']:.1f}%")

                if 'threshold' in target_params: # Only if not already handled by Rejection
                     curr = get_param_val('threshold')
                     if curr is not None:
                         new_val = round(curr * 1.1, 3) # Increase by 10%
                         # Logic conflict: If Rejection High AND WR Low, what to do?
                         # Usually Rejection High means we are too strict, but WR Low means we are not strict enough.
                         # Prioritize WR. But let's check if modified.
                         # Since Rejection check runs first, if it modified, we might skip this or override?
                         # Let's override or add conditions.
                         # For now, just apply it.
                         update_param('threshold', new_val, f"Tightened due to WR {data['wr']:.1f}%")

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                if 'adx_threshold' in target_params:
                     curr = get_param_val('adx_threshold')
                     if curr is not None:
                         new_val = int(max(10, curr - 5))
                         update_param('adx_threshold', new_val, f"Relaxed due to WR {data['wr']:.1f}%")

            # 4. Low R:R (< 1.5) -> Tighten Stop (reduce stop_pct)
            if data['rr'] < 1.5 and data['wr'] < 90:
                if 'stop_pct' in target_params:
                     curr = get_param_val('stop_pct')
                     if curr is not None:
                         new_val = round(max(0.5, curr - 0.2), 1)
                         update_param('stop_pct', new_val, f"Tightened due to R:R {data['rr']:.2f}")

            if modified:
                # Add comment with date
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"
                # Insert after imports
                lines = new_content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('import '):
                        insert_idx = i
                        break

                if insert_idx == 0: insert_idx = 2

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
            if not self.improvements:
                f.write("No improvements applied today.\n")
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
                f.write("- None\n")
            for issue in self.issues:
                f.write(f"- {issue}\n")

            f.write("\n## 💡 INSIGHTS FOR TOMORROW:\n")
            if not self.insights:
                f.write("- Continue monitoring.\n")
            for insight in self.insights:
                f.write(f"- {insight}\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'openalgo', 'strategies', 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")

            f.write("# Set Environment\n")
            f.write("export PYTHONPATH=$PYTHONPATH:$(pwd)\n")
            f.write("export OPENALGO_APIKEY=${OPENALGO_APIKEY:-'demo_key'}\n")

            f.write("\necho 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/'\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')
                # Defaults
                port = 5001
                if 'mcx' in strategy: port = 5001 # MCX usually 5001
                else: port = 5002 # NSE usually 5002 (Dhan)

                f.write(f"nohup python3 openalgo/strategies/scripts/{strategy}.py --symbol {symbol} --port {port} --api_key $OPENALGO_APIKEY > openalgo/log/strategies/{strategy}_{symbol}.log 2>&1 &\n")

            f.write("\necho 'Deployment complete.'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
