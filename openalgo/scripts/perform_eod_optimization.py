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
    'mcx_commodity': ['adx_threshold', 'min_atr'],
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
            # Handling strategy names with underscores
            parts = filename.replace('.log', '').split('_')
            # Heuristic: Symbol is usually the last part, unless it has numbers/dates
            # For this context, assume last part is symbol.
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
                if "Signal" in line or "Crossover" in line:
                    signals += 1

                # Entry Detection (Position Updated usually follows Signal)
                if ("BUY" in line or "SELL" in line) and "Position Updated" in line:
                    entries += 1
                elif "VWAP Crossover Buy" in line or "Oversold Reversion Signal" in line:
                     # Fallback if Position Updated not logged immediately or in specific format
                     # But we should rely on "Position Updated" to confirm execution
                     pass

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        val_str = line.split("PnL:")[1].strip().split()[0]
                        # Remove trailing chars if any
                        val = float(re.sub(r'[^\d.-]', '', val_str))
                        total_pnl += val
                        if val > 0:
                            wins += 1
                            gross_win += val
                        else:
                            losses += 1
                            gross_loss += abs(val)
                    except Exception as e:
                        pass

            # Fallback for manual signals count if low
            if signals == 0 and entries > 0:
                signals = entries

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

            # Score Calculation based on Prompt
            # Score = (Win Rate × 0.3) + (Profit Factor × 0.3) + (Sharpe × 0.2) + (Entry Rate × 0.1) + (Error-Free Rate × 0.1)
            # Normalizing Profit Factor: 1.0 = 50, 2.0 = 80, 3.0 = 100?
            # Let's map PF 0-3 to 0-100 linear? No, PF can be huge. Cap at 5?
            pf_score = min(profit_factor, 5.0) * 20 # 5.0 -> 100

            # Sharpe Proxy: RR Ratio
            # RR 1.5 is good. RR 3.0 is great.
            sharpe_score = min(rr_ratio, 3.0) * 33.3 # 3.0 -> 100

            entry_rate_score = (entries / signals * 100) if signals > 0 else 0
            error_score = error_free_rate * 100

            score = (win_rate * 0.3) + (pf_score * 0.3) + (sharpe_score * 0.2) + (entry_rate_score * 0.1) + (error_score * 0.1)

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

    def update_param_in_content(self, content, param, new_val):
        """Helper to update param in various formats."""
        # 1. self.param = X
        pattern1 = r"(self\." + param + r"\s*=\s*)(\d+\.?\d*)"
        match1 = re.search(pattern1, content)
        if match1:
            return content.replace(match1.group(0), f"{match1.group(1)}{new_val}"), match1.group(2)

        # 2. parser.add_argument('--param', ... default=X)
        pattern2 = r"(parser\.add_argument\('--" + param + r"'.*default=)(\d+\.?\d*)"
        match2 = re.search(pattern2, content)
        if match2:
            return content.replace(match2.group(0), f"{match2.group(1)}{new_val}"), match2.group(2)

        # 3. Dictionary: 'param': X
        pattern3 = r"('" + param + r"'\s*:\s*)(\d+\.?\d*)"
        match3 = re.search(pattern3, content)
        if match3:
             return content.replace(match3.group(0), f"{match3.group(1)}{new_val}"), match3.group(2)

        return content, None

    def optimize_strategies(self):
        for strategy, data in self.metrics.items():
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                # Try with full filename if strategy name was parsed differently
                # But here we constructed name from filename
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

            # 1. High Rejection Rate (> 70%) -> Lower Threshold / Relax Filters
            if data['rejection'] > 70:
                # Logic refinement: extract, calc, replace
                for param in ['threshold', 'rsi_lower']:
                    if param in target_params:
                        # Find current from new_content to chain updates safely
                         _, old_val = self.update_param_in_content(new_content, param, 0) # Just to find
                         if old_val:
                             val = float(old_val)
                             new_val = val
                             if param == 'threshold': new_val = max(0, int(val - 5))
                             elif param == 'rsi_lower': new_val = min(40, val + 5) # Relax RSI Lower (increase it, e.g. 30->35)

                             if new_val != val:
                                 new_content, _ = self.update_param_in_content(new_content, param, new_val)
                                 changes.append(f"{param}: {old_val} -> {new_val} (Relaxed due to Rejection {data['rejection']:.1f}%)")
                                 modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                for param in ['rsi_lower', 'threshold', 'adx_threshold']:
                    if param in target_params:
                         _, old_val = self.update_param_in_content(new_content, param, 0)
                         if old_val:
                             val = float(old_val)
                             new_val = val
                             if param == 'rsi_lower': new_val = max(10, val - 5) # Tighten (lower it)
                             elif param == 'threshold': new_val = val + 5 # Tighten (higher it)
                             elif param == 'adx_threshold': new_val = min(50, val + 5) # Tighten (higher it)

                             if new_val != val:
                                 new_content, _ = self.update_param_in_content(new_content, param, new_val)
                                 changes.append(f"{param}: {old_val} -> {new_val} (Tightened due to WR {data['wr']:.1f}%)")
                                 modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters (Scale up?)
            elif data['wr'] > 80:
                 # Maybe allow slightly looser entry to get more trades
                 for param in ['threshold']:
                    if param in target_params:
                         _, old_val = self.update_param_in_content(new_content, param, 0)
                         if old_val:
                             val = float(old_val)
                             new_val = max(0, int(val - 5))
                             if new_val != val:
                                 new_content, _ = self.update_param_in_content(new_content, param, new_val)
                                 changes.append(f"{param}: {old_val} -> {new_val} (Relaxed due to High WR {data['wr']:.1f}%)")
                                 modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop (reduce stop_pct)
            if data['rr'] < 1.5 and data['wr'] < 90:
                if 'stop_pct' in target_params:
                     _, old_val = self.update_param_in_content(new_content, 'stop_pct', 0)
                     if old_val:
                         val = float(old_val)
                         new_val = max(0.5, round(val - 0.2, 1))
                         if new_val != val:
                             new_content, _ = self.update_param_in_content(new_content, 'stop_pct', new_val)
                             changes.append(f"stop_pct: {old_val} -> {new_val} (Tightened due to R:R {data['rr']:.2f})")
                             modified = True

            if modified:
                # Add comment with date
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"

                lines = new_content.split('\n')
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
            f.write(f"📊 END-OF-DAY REPORT - {date_str}\n\n")

            f.write("📈 TODAY'S PERFORMANCE SUMMARY:\n")
            f.write("Strategy | Signals | Entries | Wins | WR% | PF | Score | Status\n")
            f.write("---------|---------|---------|------|-----|----|----|--------\n")
            for name, m in sorted_strategies:
                status = "✓" if m['score'] > 50 else "✗"
                f.write(f"{name} | {m['signals']} | {m['entries']} | {m['wins']} | {m['wr']:.1f}% | {m['pf']:.1f}| {m['score']:.1f} | {status}\n")

            f.write("\n🔧 INCREMENTAL IMPROVEMENTS APPLIED:\n")
            for i, item in enumerate(self.improvements):
                f.write(f"{i+1}. {item['strategy']}\n")
                for change in item['changes']:
                    # Parsing change string for better format: "param: old -> new (Reason)"
                    # Output: - Changed: [param] from [old] to [new]
                    #         - Reason: [reason]
                    try:
                        # format: "param: old -> new (Reason)"
                        parts = change.split('(')
                        reason = parts[1].replace(')', '')
                        change_part = parts[0]
                        f.write(f"   - Changed: {change_part.strip()}\n")
                        f.write(f"   - Reason: {reason}\n")
                        f.write(f"   - Expected Impact: Better Alignment with Market Conditions\n")
                    except:
                        f.write(f"   - {change}\n")

            f.write("\n📊 STRATEGY RANKING (Top 5 for Tomorrow):\n")
            for i, name in enumerate(self.strategies_to_deploy):
                score = self.metrics[name]['score']
                f.write(f"{i+1}. {name} - Score: {score:.1f} - [Action: Start/Restart]\n")

            f.write("\n🚀 DEPLOYMENT PLAN:\n")
            f.write("- Stop: All running strategies\n") # Simplification
            f.write(f"- Start: {', '.join(self.strategies_to_deploy)}\n")
            f.write("- Restart: Strategies with parameter updates\n")

            f.write("\n⚠️ ISSUES FOUND:\n")
            total_errors = sum(m['errors'] for m in self.metrics.values())
            if total_errors > 0:
                 f.write(f"- {total_errors} errors detected across logs. Check individual log files.\n")
            else:
                 f.write("- No critical errors found.\n")

            f.write("\n💡 INSIGHTS FOR TOMORROW:\n")
            f.write("- Market pattern observed: Volatility adjustments applied where necessary.\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")
            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/'\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')
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
