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
    'supertrend_vwap': ['threshold', 'stop_pct', 'adx_threshold'],
    'mcx_commodity_momentum': ['adx_threshold', 'min_atr', 'seasonality_score', 'global_alignment_score'],
    'ai_hybrid': ['rsi_lower', 'rsi_upper', 'stop_pct'],
    'orb': ['range_minutes', 'stop_loss_pct'],
    'default': ['threshold', 'stop_pct', 'stop_loss_pct', 'target_pct']
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
            # e.g., supertrend_vwap_strategy_NIFTY.log
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

            for line in lines:
                if "Error" in line or "Exception" in line:
                    errors += 1

                # Signal Detection
                # Catch generic "Signal generated" or strategy specific signals
                if "Signal generated" in line or "BUY SIGNAL" in line or "SELL SIGNAL" in line:
                    signals += 1

                # Entry Detection
                if "Order Placed" in line or "Entry:" in line:
                    entries += 1
                elif "Skipping new entries" in line:
                    # Count as a signal that was rejected
                    signals += 1

                # Exit / PnL Detection
                # Catch "Closed Long. PnL: X" or "PnL: X"
                if "PnL:" in line:
                    try:
                        # Split by "PnL:" and take the part after
                        val_str = line.split("PnL:")[1].strip().split()[0]
                        val = float(val_str)
                        total_pnl += val
                        if val > 0:
                            wins += 1
                            gross_win += val
                        else:
                            losses += 1
                            gross_loss += abs(val)
                    except: pass
                elif "Trailing Stop Hit" in line:
                    # Fallback if PnL not logged explicitly, assume small win or breakeven
                    wins += 1 # Assumption for this specific log format
                    gross_win += 10 # Dummy small win
                elif "Price crossed below VWAP" in line:
                    # Fallback exit logic
                    losses += 1
                    gross_loss += 10 # Dummy small loss

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
            # User Formula: Score = (Win Rate × 0.3) + (Profit Factor × 0.3) + (Sharpe × 0.2) + (Entry Rate × 0.1) + (Error-Free Rate × 0.1)

            # Normalize PF (0-3 -> 0-100 approx)
            pf_score = min(profit_factor, 3.0) / 3.0 * 100

            # Sharpe Proxy using RR (0-3 -> 0-100 approx)
            sharpe_score = min(rr_ratio, 3.0) / 3.0 * 100

            # Entry Rate (Entries/Signals) * 100
            entry_rate = (entries / signals * 100) if signals > 0 else 0

            # Error Free Rate * 100
            error_score = error_free_rate * 100

            score = (win_rate * 0.3) + (pf_score * 0.3) + (sharpe_score * 0.2) + (entry_rate * 0.1) + (error_score * 0.1)

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
                # Try finding without '_strategy' suffix or similar variations if needed
                # For now assume exact match
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

            # Helper to update param in content
            def update_param(param_name, adjustment_func, reason):
                nonlocal new_content, modified, changes

                # Try updating self.param = val
                # Regex: self.param = 100 or self.param=100
                pattern_self = r"(self\." + re.escape(param_name) + r"\s*=\s*)(\d+\.?\d*)"
                match_self = re.search(pattern_self, new_content)

                if match_self:
                    current_val = float(match_self.group(2))
                    # Check if int or float in original
                    is_int = '.' not in match_self.group(2)
                    new_val = adjustment_func(current_val)
                    if is_int: new_val = int(new_val)

                    new_str = f"{match_self.group(1)}{new_val}"
                    new_content = new_content.replace(match_self.group(0), new_str)
                    changes.append(f"{param_name}: {current_val} -> {new_val} ({reason})")
                    modified = True
                    return

                # Try updating PARAMS dict or DEFAULT_PARAMS dict
                # Regex: 'param': 100 or "param": 100
                pattern_dict = r"(['\"]" + re.escape(param_name) + r"['\"]\s*:\s*)(\d+\.?\d*)"
                match_dict = re.search(pattern_dict, new_content)

                if match_dict:
                    current_val = float(match_dict.group(2))
                    is_int = '.' not in match_dict.group(2)
                    new_val = adjustment_func(current_val)
                    if is_int: new_val = int(new_val)

                    new_str = f"{match_dict.group(1)}{new_val}"
                    new_content = new_content.replace(match_dict.group(0), new_str)
                    changes.append(f"{param_name}: {current_val} -> {new_val} ({reason})")
                    modified = True
                    return

                # Try updating argparse default
                pattern_arg = r"(parser\.add_argument\('--" + re.escape(param_name) + r"'.*default=)(\d+\.?\d*)"
                match_arg = re.search(pattern_arg, new_content)

                if match_arg:
                    current_val = float(match_arg.group(2))
                    is_int = '.' not in match_arg.group(2)
                    new_val = adjustment_func(current_val)
                    if is_int: new_val = int(new_val)

                    new_str = f"{match_arg.group(1)}{new_val}"
                    new_content = new_content.replace(match_arg.group(0), new_str)
                    changes.append(f"{param_name}: {current_val} -> {new_val} ({reason})")
                    modified = True
                    return

            # 1. High Rejection Rate (> 70%) -> Lower Threshold / Relax Filters
            if data['rejection'] > 70:
                if 'threshold' in target_params:
                    update_param('threshold', lambda x: max(0, x - 5), f"Lowered due to Rejection {data['rejection']:.1f}%")
                elif 'seasonality_score' in target_params:
                    update_param('seasonality_score', lambda x: max(30, x - 5), f"Relaxed due to Rejection {data['rejection']:.1f}%")

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                if 'adx_threshold' in target_params:
                    update_param('adx_threshold', lambda x: min(50, x + 5), f"Tightened due to WR {data['wr']:.1f}%")
                elif 'rsi_lower' in target_params: # For mean reversion
                    update_param('rsi_lower', lambda x: max(10, x - 5), f"Tightened due to WR {data['wr']:.1f}%")
                elif 'threshold' in target_params and not modified:
                    update_param('threshold', lambda x: x + 5, f"Tightened due to WR {data['wr']:.1f}%")

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                if 'adx_threshold' in target_params:
                    update_param('adx_threshold', lambda x: max(15, x - 5), f"Relaxed due to WR {data['wr']:.1f}%")
                elif 'rsi_lower' in target_params:
                    update_param('rsi_lower', lambda x: min(40, x + 5), f"Relaxed due to WR {data['wr']:.1f}%")
                elif 'threshold' in target_params:
                    update_param('threshold', lambda x: max(0, x - 5), f"Relaxed due to WR {data['wr']:.1f}%")

            # 4. Low R:R (< 1.5) -> Tighten Stop (reduce stop_pct)
            if data['rr'] < 1.5 and data['wr'] < 90:
                if 'stop_pct' in target_params:
                    update_param('stop_pct', lambda x: max(0.5, x - 0.2), f"Tightened due to R:R {data['rr']:.2f}")

            if modified:
                # Add comment with date
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"

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
            f.write("- Start: The following strategies:\n")
            for name in self.strategies_to_deploy:
                f.write(f"  - {name}\n")
            f.write("- Verify: Check process list\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")

            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/' || true\n\n")
            f.write("sleep 2\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')
                f.write(f"nohup python3 openalgo/strategies/scripts/{strategy}.py --symbol {symbol} --api_key $OPENALGO_APIKEY > openalgo/log/strategies/{strategy}_{symbol}.log 2>&1 &\n")
                f.write("sleep 1\n")

            f.write("\necho 'Verifying deployment...'\n")
            f.write("sleep 2\n")
            f.write("echo 'Running processes:'\n")
            f.write("pgrep -a -f 'python3 openalgo/strategies/scripts/'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
