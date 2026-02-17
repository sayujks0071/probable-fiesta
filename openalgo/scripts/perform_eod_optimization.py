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
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # openalgo root
# Trace back: openalgo/scripts -> REPO_ROOT is two levels up?
# If script is in openalgo/scripts, REPO_ROOT is .. (openalgo) -> .. (root)
# Actually, the file structure shown in 'list_files' for openalgo/scripts is ./ ../
# So openalgo/scripts is one level inside openalgo.
# If repo root is /app, then openalgo is /app/openalgo.
# SCRIPT_DIR = /app/openalgo/scripts
# REPO_ROOT = /app

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Assuming running from repo root or openalgo/scripts
# Let's try to find 'openalgo' dir
if os.path.basename(SCRIPT_DIR) == 'scripts':
    REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
else:
    REPO_ROOT = SCRIPT_DIR

LOG_DIR = os.path.join(REPO_ROOT, 'openalgo', 'log', 'strategies')
STRATEGIES_DIR = os.path.join(REPO_ROOT, 'openalgo', 'strategies', 'scripts')
REPORTS_DIR = os.path.join(REPO_ROOT, 'openalgo', 'reports')

os.makedirs(REPORTS_DIR, exist_ok=True)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("EOD_Optimizer")

# Tunable Parameters Definition
TUNABLE_PARAMS = {
    'supertrend_vwap': ['threshold', 'stop_pct'],
    'ai_hybrid': ['rsi_lower', 'rsi_upper', 'stop_pct'],
    'mcx_commodity_momentum': ['adx_threshold', 'min_atr'],
    'default': ['threshold', 'stop_pct', 'stop_loss_pct', 'target_pct']
}

class StrategyOptimizer:
    def __init__(self):
        self.metrics = {}
        self.strategies_to_deploy = []
        self.improvements = []

    def parse_logs(self):
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        logger.info(f"Found {len(log_files)} log files in {LOG_DIR}")

        for log_file in log_files:
            filename = os.path.basename(log_file)
            # Assuming filename format: strategy_name_SYMBOL.log
            # But strategy names can have underscores.
            # Strategy names usually match the python file name.
            # E.g. supertrend_vwap_strategy_NIFTY.log -> supertrend_vwap_strategy

            # Heuristic: split by '_' and assume the last part is Symbol
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
                # Matches "Signal detected" or specific strategy logs
                if "Signal" in line or "Crossover" in line or "Condition Met" in line:
                    signals += 1

                # Entry Detection
                if "BUY" in line or "SELL" in line:
                    # Filter out signal lines if they contain BUY/SELL
                    if "Signal" not in line and "Condition" not in line:
                        entries += 1
                    # Special case for some logs where entry is same line as signal
                    elif "executing" in line.lower():
                        entries += 1

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
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

            # Adjustments for dummy log patterns
            # AI Hybrid: "Oversold Reversion Signal... BUY." -> Is this entry or signal?
            # It says "Signal... BUY".
            # If there are no other BUY lines, this counts as entry?
            # Let's count "Signal" as Signal.
            # If "BUY" is in the same line, maybe it counts as Entry too?
            # For robust parsing, let's assume Entry count <= Signal count.

            if entries == 0 and signals > 0:
                 # Fallback: maybe every signal was an entry?
                 entries = signals

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (999 if wins > 0 else 0)

            # Rejection Rate: 1 - (Entries / Signals)
            # If Entries > Signals (logging artifact), set to 0
            rejection_rate = (1 - (entries / signals)) * 100 if signals > 0 else 0
            if rejection_rate < 0: rejection_rate = 0

            # Avg R:R
            avg_win = gross_win / wins if wins > 0 else 0
            avg_loss = gross_loss / losses if losses > 0 else 0
            rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            error_free_rate = 1.0
            if errors > 0:
                error_free_rate = max(0, 1 - (errors / (len(lines) if len(lines) > 0 else 1)))

            # Score Calculation
            # Normalize components to 0-100 scale for weighting
            norm_wr = win_rate
            norm_pf = min(profit_factor * 20, 100) # PF 5.0 -> 100
            norm_rr = min(rr_ratio * 33, 100) # RR 3.0 -> 100

            entry_rate = (entries/signals) if signals > 0 else 0
            norm_entry = entry_rate * 100

            norm_error = error_free_rate * 100

            score = (norm_wr * 0.3) + (norm_pf * 0.3) + (norm_rr * 0.2) + (norm_entry * 0.1) + (norm_error * 0.1)

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
                # Try finding it recursively or exact match
                # Strategy name might be 'supertrend_vwap_strategy' but file is same
                pass

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

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                if 'threshold' in target_params:
                    # Look for self.threshold = X
                    match = re.search(r"(self\.threshold\s*=\s*)(\d+)", new_content)
                    if match:
                        current_val = int(match.group(2))
                        new_val = max(10, current_val - 5)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"threshold: {current_val} -> {new_val} (Lowered due to Rejection {data['rejection']:.1f}%)")
                        modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                # AI Hybrid: rsi_lower (make it lower to be stricter for oversold)
                if 'rsi_lower' in target_params:
                     # Argparse default
                     match = re.search(r"(parser\.add_argument\('--rsi_lower'.*default=)(\d+\.?\d*)", new_content)
                     if match:
                        current_val = float(match.group(2))
                        new_val = max(10, current_val - 5)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"rsi_lower: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                        modified = True

                # SuperTrend: Increase threshold
                if 'threshold' in target_params and not modified:
                     match = re.search(r"(self\.threshold\s*=\s*)(\d+)", new_content)
                     if match:
                        current_val = int(match.group(2))
                        new_val = current_val + 5
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"threshold: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                        modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                # MCX Momentum: Relax ADX (DEFAULT_PARAMS['adx_threshold'])
                if 'adx_threshold' in target_params:
                    # Regex for DEFAULT_PARAMS dict entry
                    match = re.search(r"('adx_threshold':\s*)(\d+)", new_content)
                    if match:
                        current_val = int(match.group(2))
                        new_val = max(10, current_val - 5)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                        changes.append(f"adx_threshold: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                        modified = True
                    else:
                        # Try self.adx_threshold
                        match = re.search(r"(self\.adx_threshold\s*=\s*)(\d+)", new_content)
                        if match:
                            current_val = int(match.group(2))
                            new_val = max(10, current_val - 5)
                            new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
                            changes.append(f"adx_threshold: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop (reduce stop_pct)
            if data['rr'] < 1.5 and data['wr'] < 90: # If WR is super high (90+), low RR is acceptable
                if 'stop_pct' in target_params:
                    # Check class attr
                    match = re.search(r"(self\.stop_pct\s*=\s*)(\d+\.?\d*)", new_content)
                    if match:
                        current_val = float(match.group(2))
                        new_val = max(0.5, current_val - 0.2)
                        new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val:.1f}")
                        changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {data['rr']:.2f})")
                        modified = True
                    else:
                        # Check argparse
                        match = re.search(r"(parser\.add_argument\('--stop_pct'.*default=)(\d+\.?\d*)", new_content)
                        if match:
                             current_val = float(match.group(2))
                             new_val = max(0.5, current_val - 0.2)
                             new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val:.1f}")
                             changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {data['rr']:.2f})")
                             modified = True

            if modified:
                # Add comment with date
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"

                lines = new_content.split('\n')
                # Insert after shebang or docstring
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('"""') and i > 0: # End of docstring
                        insert_idx = i + 1
                        break
                    if line.startswith('import '):
                        insert_idx = i
                        break

                if insert_idx == 0 and len(lines) > 0 and lines[0].startswith("#!"):
                    insert_idx = 1

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
            f.write("- Stop: Underperforming strategies not in Top 5.\n")
            f.write("- Start: Top 5 strategies.\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'openalgo', 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")

            f.write("# Set Environment\n")
            f.write("export OPENALGO_APIKEY=${OPENALGO_APIKEY:-'YOUR_API_KEY'}\n")
            f.write("export OPENALGO_HOST=${OPENALGO_HOST:-'http://127.0.0.1:5001'}\n\n")

            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/' || true\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')
                # Construct command
                # Use nohup and redirect logs
                log_file = f"openalgo/log/strategies/{strategy}_{symbol}.log"
                cmd = f"nohup python3 openalgo/strategies/scripts/{strategy}.py --symbol {symbol} > {log_file} 2>&1 &"
                f.write(f"echo 'Starting {strategy} on {symbol}'\n")
                f.write(f"{cmd}\n")

            f.write("\necho 'Deployment complete.'\n")
            f.write("ps aux | grep 'openalgo/strategies/scripts/'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
