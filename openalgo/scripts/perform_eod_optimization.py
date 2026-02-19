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
    'supertrend_vwap': ['threshold', 'stop_pct'],
    'ai_hybrid': ['rsi_lower', 'rsi_upper', 'stop_pct'],
    'opening_range': ['range_minutes', 'stop_loss_pct'],
    'orb': ['range_minutes', 'stop_loss_pct'],
    'advanced_ml_momentum': ['threshold', 'stop_pct'],
    'default': ['threshold', 'stop_pct', 'stop_loss_pct', 'target_pct']
}

class StrategyOptimizer:
    def __init__(self):
        # Structure: metrics[strategy_name] = {'total': {}, 'symbols': {symbol: {}}}
        self.metrics = {}
        self.strategies_to_deploy = []
        self.improvements = []

    def parse_logs(self):
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        logger.info(f"Found {len(log_files)} log files.")

        for log_file in log_files:
            filename = os.path.basename(log_file)
            parts = filename.replace('.log', '').split('_')
            symbol = parts[-1]
            strategy_name = "_".join(parts[:-1])

            if strategy_name not in self.metrics:
                self.metrics[strategy_name] = {
                    'total': {
                        'signals': 0, 'entries': 0, 'wins': 0, 'losses': 0,
                        'gross_win': 0.0, 'gross_loss': 0.0, 'errors': 0,
                        'morning_wins': 0, 'morning_losses': 0,
                        'afternoon_wins': 0, 'afternoon_losses': 0
                    },
                    'symbols': {}
                }

            with open(log_file, 'r') as f:
                lines = f.readlines()

            signals = 0
            entries = 0
            wins = 0
            losses = 0
            gross_win = 0.0
            gross_loss = 0.0
            errors = 0

            morning_wins = 0
            morning_losses = 0
            afternoon_wins = 0
            afternoon_losses = 0

            for line in lines:
                timestamp = None
                try:
                    ts_str = line[:19]
                    timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except:
                    pass

                if "Error" in line or "Exception" in line:
                    errors += 1

                if "Signal" in line or "Crossover" in line:
                    signals += 1

                if "Order placed" in line:
                    entries += 1

                pnl = 0.0
                is_win = False
                is_loss = False

                if "PnL:" in line:
                    try:
                        pnl = float(line.split("PnL:")[1].strip().split()[0])
                        if pnl > 0:
                            wins += 1
                            gross_win += pnl
                            is_win = True
                        else:
                            losses += 1
                            gross_loss += abs(pnl)
                            is_loss = True
                    except: pass

                if timestamp and (is_win or is_loss):
                    if timestamp.hour < 12 or (timestamp.hour == 12 and timestamp.minute < 30):
                        if is_win: morning_wins += 1
                        if is_loss: morning_losses += 1
                    else:
                        if is_win: afternoon_wins += 1
                        if is_loss: afternoon_losses += 1

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (999 if wins > 0 else 0)
            rejection_rate = (1 - (entries / signals)) * 100 if signals > 0 else 0

            avg_win = gross_win / wins if wins > 0 else 0
            avg_loss = gross_loss / losses if losses > 0 else 0
            rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            error_free_rate = 1.0
            if errors > 0:
                error_free_rate = max(0, 1 - (errors / (len(lines) if len(lines) > 0 else 1)))

            score = (win_rate * 0.3) + (min(profit_factor, 10) * 10 * 0.3) + (min(rr_ratio, 3.0) * 20 * 0.2) + ((entries/signals if signals else 0) * 100 * 0.1) + (error_free_rate * 100 * 0.1)

            self.metrics[strategy_name]['symbols'][symbol] = {
                'signals': signals, 'entries': entries, 'wins': wins, 'losses': losses,
                'wr': win_rate, 'pf': profit_factor, 'rr': rr_ratio, 'rejection': rejection_rate,
                'errors': errors, 'score': score
            }

            t = self.metrics[strategy_name]['total']
            t['signals'] += signals
            t['entries'] += entries
            t['wins'] += wins
            t['losses'] += losses
            t['gross_win'] += gross_win
            t['gross_loss'] += gross_loss
            t['errors'] += errors
            t['morning_wins'] += morning_wins
            t['morning_losses'] += morning_losses
            t['afternoon_wins'] += afternoon_wins
            t['afternoon_losses'] += afternoon_losses

        for strat in self.metrics:
            t = self.metrics[strat]['total']
            total_trades = t['wins'] + t['losses']
            t['wr'] = (t['wins'] / total_trades * 100) if total_trades > 0 else 0
            t['pf'] = (t['gross_win'] / t['gross_loss']) if t['gross_loss'] > 0 else (999 if t['wins'] > 0 else 0)
            t['rejection'] = (1 - (t['entries'] / t['signals'])) * 100 if t['signals'] > 0 else 0

            avg_win = t['gross_win'] / t['wins'] if t['wins'] > 0 else 0
            avg_loss = t['gross_loss'] / t['losses'] if t['losses'] > 0 else 0
            t['rr'] = avg_win / avg_loss if avg_loss > 0 else 0

            t['score'] = (t['wr'] * 0.3) + (min(t['pf'], 10) * 10 * 0.3) + (min(t['rr'], 3.0) * 20 * 0.2) + ((t['entries']/t['signals'] if t['signals'] else 0) * 100 * 0.1)
            if t['errors'] > 0:
                t['score'] -= min(10, t['errors'] * 2)

    def optimize_strategies(self):
        for strategy, metrics_data in self.metrics.items():
            data = metrics_data['total']
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                logger.warning(f"Strategy file not found: {filepath}")
                continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            modified = False
            changes = []

            target_params = TUNABLE_PARAMS.get('default', [])
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_params = TUNABLE_PARAMS[key]
                    break

            # Helper for regex replacement
            def replace_param(content, param_name, current_val, new_val, reason):
                # Try self.param = val
                pattern_self = r"(self\." + param_name + r"\s*=\s*)(\d+(\.\d*)?)"
                match = re.search(pattern_self, content)
                if match:
                    if '.' in str(new_val):
                         repl = f"{match.group(1)}{new_val:.4f}".rstrip('0').rstrip('.')
                    else:
                         repl = f"{match.group(1)}{int(new_val)}"
                    new_c = content.replace(match.group(0), repl)
                    return new_c, True

                # Try parser default
                pattern_parser = r"(parser\.add_argument\('--" + param_name + r"'.*default=)(\d+(\.\d*)?)"
                match = re.search(pattern_parser, content)
                if match:
                    if '.' in str(new_val):
                         repl = f"{match.group(1)}{new_val:.4f}".rstrip('0').rstrip('.')
                    else:
                         repl = f"{match.group(1)}{int(new_val)}"
                    new_c = content.replace(match.group(0), repl)
                    return new_c, True

                return content, False

            # Helper to get current value
            def get_param_value(content, param_name):
                # Try self.param = val
                pattern_self = r"(self\." + param_name + r"\s*=\s*)(\d+(\.\d*)?)"
                match = re.search(pattern_self, content)
                if match:
                    return float(match.group(2))

                # Try parser default
                pattern_parser = r"(parser\.add_argument\('--" + param_name + r"'.*default=)(\d+(\.\d*)?)"
                match = re.search(pattern_parser, content)
                if match:
                    return float(match.group(2))
                return None


            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                if 'threshold' in target_params:
                    current_val = get_param_value(content, 'threshold')
                    if current_val is not None:
                        if current_val < 1.0: step = 0.002
                        else: step = 5
                        new_val = max(0, current_val - step)
                        new_content, applied = replace_param(new_content, 'threshold', current_val, new_val, "")
                        if applied:
                            changes.append(f"threshold: {current_val} -> {new_val} (Lowered due to Rejection {data['rejection']:.1f}%)")
                            modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                if 'rsi_lower' in target_params:
                     current_val = get_param_value(content, 'rsi_lower')
                     if current_val is not None:
                        new_val = max(10, current_val - 5)
                        new_content, applied = replace_param(new_content, 'rsi_lower', current_val, new_val, "")
                        if applied:
                            changes.append(f"rsi_lower: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                            modified = True

                if 'threshold' in target_params and not modified:
                     current_val = get_param_value(content, 'threshold')
                     if current_val is not None:
                        if current_val < 1.0: step = 0.002
                        else: step = 5
                        new_val = current_val + step
                        new_content, applied = replace_param(new_content, 'threshold', current_val, new_val, "")
                        if applied:
                            changes.append(f"threshold: {current_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                            modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                if 'rsi_lower' in target_params:
                     current_val = get_param_value(content, 'rsi_lower')
                     if current_val is not None:
                        new_val = min(40, current_val + 5)
                        new_content, applied = replace_param(new_content, 'rsi_lower', current_val, new_val, "")
                        if applied:
                            changes.append(f"rsi_lower: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

                if 'threshold' in target_params:
                     current_val = get_param_value(content, 'threshold')
                     if current_val is not None:
                        if current_val < 1.0: step = 0.002
                        else: step = 5
                        new_val = max(0, current_val - step)
                        new_content, applied = replace_param(new_content, 'threshold', current_val, new_val, "")
                        if applied:
                            changes.append(f"threshold: {current_val} -> {new_val} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop
            if data['rr'] < 1.5 and data['wr'] < 80:
                if 'stop_pct' in target_params:
                    current_val = get_param_value(content, 'stop_pct')
                    if current_val is not None:
                        new_val = max(0.5, current_val - 0.2)
                        new_content, applied = replace_param(new_content, 'stop_pct', current_val, new_val, "")
                        if applied:
                            changes.append(f"stop_pct: {current_val} -> {new_val:.1f} (Tightened due to R:R {data['rr']:.2f})")
                            modified = True

            if modified:
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"
                lines = new_content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith('"""') and i > 0:
                        insert_idx = i + 1
                        break
                    if line.startswith('import ') and insert_idx == 0:
                        insert_idx = i
                        break

                if insert_idx == 0 and len(lines) > 1: insert_idx = 1

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

        sorted_strategies = sorted(self.metrics.items(), key=lambda x: x[1]['total']['score'], reverse=True)
        self.strategies_to_deploy = [s[0] for s in sorted_strategies[:5]]

        with open(report_file, 'w') as f:
            f.write(f"# 📊 END-OF-DAY REPORT - {date_str}\n\n")

            f.write("## 📈 TODAY'S PERFORMANCE SUMMARY:\n")
            f.write("| Strategy | Signals | Entries | Wins | WR% | PF | R:R | Rej% | Score | Status |\n")
            f.write("|----------|---------|---------|------|-----|----|-----|------|-------|--------|\n")

            for name, data in sorted_strategies:
                m = data['total']
                status = "✓" if m['score'] > 50 else "✗"
                f.write(f"| **{name}** | {m['signals']} | {m['entries']} | {m['wins']} | {m['wr']:.1f}% | {m['pf']:.1f} | {m['rr']:.2f} | {m['rejection']:.1f}% | {m['score']:.1f} | {status} |\n")
                for symbol, sm in data['symbols'].items():
                     f.write(f"| └ {symbol} | {sm['signals']} | {sm['entries']} | {sm['wins']} | {sm['wr']:.1f}% | {sm['pf']:.1f} | {sm['rr']:.2f} | {sm['rejection']:.1f}% | {sm['score']:.1f} | - |\n")

            f.write("\n## 🔧 INCREMENTAL IMPROVEMENTS APPLIED:\n")
            for item in self.improvements:
                f.write(f"### {item['strategy']}\n")
                for change in item['changes']:
                    f.write(f"- {change}\n")

            f.write("\n## ⏱ TIME OF DAY PERFORMANCE:\n")
            f.write("| Strategy | Morning WR% (Wins/Loss) | Afternoon WR% (Wins/Loss) |\n")
            f.write("|----------|-------------------------|---------------------------|\n")
            for name, data in sorted_strategies:
                m = data['total']
                m_trades = m['morning_wins'] + m['morning_losses']
                m_wr = (m['morning_wins'] / m_trades * 100) if m_trades > 0 else 0
                a_trades = m['afternoon_wins'] + m['afternoon_losses']
                a_wr = (m['afternoon_wins'] / a_trades * 100) if a_trades > 0 else 0
                f.write(f"| {name} | {m_wr:.1f}% ({m['morning_wins']}/{m['morning_losses']}) | {a_wr:.1f}% ({m['afternoon_wins']}/{m['afternoon_losses']}) |\n")

            f.write("\n## 📊 STRATEGY RANKING (Top 5 for Tomorrow):\n")
            for i, name in enumerate(self.strategies_to_deploy):
                score = self.metrics[name]['total']['score']
                f.write(f"{i+1}. {name} - Score: {score:.1f} - Action: Start/Restart\n")

            f.write("\n## 💡 INSIGHTS:\n")
            best_strat = sorted_strategies[0][0] if sorted_strategies else "None"
            worst_strat = sorted_strategies[-1][0] if sorted_strategies else "None"
            f.write(f"- **Best Performer**: {best_strat}\n")
            f.write(f"- **Worst Performer**: {worst_strat}\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")
            f.write("echo 'Stopping strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/' || true\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                symbols = self.metrics.get(strategy, {}).get('symbols', {}).keys()
                if not symbols:
                    symbols = ['NIFTY']

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
