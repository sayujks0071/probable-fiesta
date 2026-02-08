#!/usr/bin/env python3
import os
import re
import glob
import logging
import argparse
from datetime import datetime
import sys

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
    'gap_fade': ['threshold', 'gap_threshold', 'qty'],
    'mcx_commodity_momentum': ['adx_threshold', 'rsi_lower', 'rsi_upper', 'stop_pct'],
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
            # Special case for strategies with underscores
            parts = filename.replace('.log', '').rsplit('_', 1)
            if len(parts) == 2:
                strategy_name = parts[0]
                symbol = parts[1]
            else:
                strategy_name = filename.replace('.log', '')
                symbol = 'UNKNOWN'

            with open(log_file, 'r') as f:
                lines = f.readlines()

            signals = 0
            entries = 0
            wins = 0
            losses = 0
            gross_win = 0.0
            gross_loss = 0.0
            errors = 0

            for line in lines:
                if "Error" in line or "Exception" in line:
                    errors += 1

                # Signal Detection
                if "Signal generated" in line or "Signal" in line or "Crossover" in line:
                    signals += 1

                # Entry Detection
                if "BUY" in line or "SELL" in line:
                    # Some logs might have "Signal generated: BUY", count distinct entries
                    if "executed" in line or "Order Placed" in line or "BUY executed" in line:
                        entries += 1
                    elif "Signal" not in line: # Fallback for simple "BUY" line
                        entries += 1

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

            # Deduplicate entries if log format caused double counting (e.g. signal+entry logs)
            # Assume entries <= signals
            if entries > signals and signals > 0:
                entries = signals

            # Recalculate based on totals
            total_trades = wins + losses

            # If we have entries but no PnL logs (e.g. just started), assume flat
            if entries > 0 and total_trades == 0:
                # Can't calc WR
                win_rate = 0.0
                profit_factor = 0.0
            else:
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if wins > 0 else 0.0)

            rejection_rate = (1 - (entries / signals)) * 100 if signals > 0 else 0.0

            # Avg R:R
            avg_win = gross_win / wins if wins > 0 else 0
            avg_loss = gross_loss / losses if losses > 0 else 0
            rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            error_free_rate = 1.0
            if errors > 0:
                error_free_rate = max(0, 1 - (errors / (len(lines) if len(lines) > 0 else 1)))

            # Score Calculation
            # Score = (Win Rate × 0.3) + (Profit Factor × 0.3) + (Sharpe × 0.2) + (Entry Rate × 0.1) + (Error-Free Rate × 0.1)
            # Normalize inputs:
            # WR: 0-1
            # PF: Cap at 3.0 -> 0-1 (div by 3)
            # Sharpe: Cap at 3.0 -> 0-1 (div by 3) - Use RR as proxy
            # Entry Rate: Entries/Signals -> 0-1
            # Error Free: 0-1

            wr_norm = win_rate / 100.0
            pf_norm = min(profit_factor, 3.0) / 3.0
            sharpe_proxy_norm = min(rr_ratio, 3.0) / 3.0
            entry_rate = (entries / signals) if signals > 0 else 0.0

            # Weightings as requested, scaled to 0-100 for readability
            score = (wr_norm * 30) + (pf_norm * 30) + (sharpe_proxy_norm * 20) + (entry_rate * 10) + (error_free_rate * 10)

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

    def _update_param(self, content, param_name, new_val):
        # 1. Try "self.param = X"
        pattern_self = re.compile(rf"(self\.{param_name}\s*=\s*)(\d+\.?\d*)")
        match_self = pattern_self.search(content)
        if match_self:
            old_val = match_self.group(2)
            new_content = content.replace(match_self.group(0), f"{match_self.group(1)}{new_val}")
            return new_content, old_val

        # 2. Try "parser.add_argument('--param', ... default=X)"
        # Handle ' or " quotes
        pattern_arg = re.compile(rf"(parser\.add_argument\(['\"]--{param_name}['\"].*default=)(\d+\.?\d*)")
        match_arg = pattern_arg.search(content)
        if match_arg:
            old_val = match_arg.group(2)
            new_content = content.replace(match_arg.group(0), f"{match_arg.group(1)}{new_val}")
            return new_content, old_val

        # 3. Try dict key "'param': X" or " 'param': X"
        pattern_dict = re.compile(rf"(['\"]{param_name}['\"]\s*:\s*)(\d+\.?\d*)")
        match_dict = pattern_dict.search(content)
        if match_dict:
            old_val = match_dict.group(2)
            new_content = content.replace(match_dict.group(0), f"{match_dict.group(1)}{new_val}")
            return new_content, old_val

        return content, None

    def optimize_strategies(self):
        for strategy, data in self.metrics.items():
            # Find file
            # Strategy name might be partial match or exact
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                 # Try finding matching file
                 candidates = glob.glob(os.path.join(STRATEGIES_DIR, f"*{strategy}*.py"))
                 if candidates:
                     filepath = candidates[0]
                 else:
                     logger.warning(f"Strategy file not found for {strategy}")
                     continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            modified = False
            changes = []

            # Determine params to check
            target_params = TUNABLE_PARAMS.get('default', [])
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_params = TUNABLE_PARAMS[key]
                    break

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                param_candidates = ['threshold', 'gap_threshold', 'adx_threshold']
                param = next((p for p in param_candidates if p in target_params), None)

                if param:
                    # Read current value first to know if we are lowering int or float
                    # Actually _update_param expects us to provide new value
                    # We need to extract value first. Let's reuse _update_param logic slightly or regex

                    # Hack: Regex search again to get val
                    match_val = None
                    for p_regex in [
                        rf"self\.{param}\s*=\s*(\d+\.?\d*)",
                        rf"parser\.add_argument\(['\"]--{param}['\"].*default=(\d+\.?\d*)",
                        rf"['\"]{param}['\"]\s*:\s*(\d+\.?\d*)"
                    ]:
                        m = re.search(p_regex, content)
                        if m:
                            match_val = m.group(1)
                            break

                    if match_val:
                        is_float = '.' in match_val
                        curr = float(match_val)
                        # Lower by ~5% or fixed amount
                        new_val = curr * 0.95 if is_float else int(curr - 5)
                        if new_val < 0: new_val = 0

                        if is_float:
                            new_val_str = f"{new_val:.2f}"
                        else:
                            new_val_str = str(int(new_val))

                        new_content, old_val = self._update_param(new_content, param, new_val_str)
                        if old_val:
                            changes.append(f"{param}: {old_val} -> {new_val_str} (Lowered due to Rejection {data['rejection']:.1f}%)")
                            modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60 and data['entries'] > 0:
                 param_candidates = ['adx_threshold', 'threshold', 'gap_threshold']
                 param = next((p for p in param_candidates if p in target_params), None)

                 if param and not modified: # Avoid conflicting changes
                    match_val = None
                    for p_regex in [
                        rf"self\.{param}\s*=\s*(\d+\.?\d*)",
                        rf"parser\.add_argument\(['\"]--{param}['\"].*default=(\d+\.?\d*)",
                        rf"['\"]{param}['\"]\s*:\s*(\d+\.?\d*)"
                    ]:
                        m = re.search(p_regex, content)
                        if m:
                            match_val = m.group(1)
                            break

                    if match_val:
                        is_float = '.' in match_val
                        curr = float(match_val)
                        # Tighten (Increase threshold usually implies tighter filter for momentum/breakout)
                        # For Gap Fade, Gap Threshold increase = Tighter
                        new_val = curr * 1.05 if is_float else int(curr + 5)

                        if is_float: new_val_str = f"{new_val:.2f}"
                        else: new_val_str = str(int(new_val))

                        new_content, old_val = self._update_param(new_content, param, new_val_str)
                        if old_val:
                            changes.append(f"{param}: {old_val} -> {new_val_str} (Tightened due to WR {data['wr']:.1f}%)")
                            modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80 and data['entries'] > 5:
                 param_candidates = ['adx_threshold', 'threshold', 'gap_threshold']
                 param = next((p for p in param_candidates if p in target_params), None)

                 if param and not modified:
                    match_val = None
                    for p_regex in [
                        rf"self\.{param}\s*=\s*(\d+\.?\d*)",
                        rf"parser\.add_argument\(['\"]--{param}['\"].*default=(\d+\.?\d*)",
                        rf"['\"]{param}['\"]\s*:\s*(\d+\.?\d*)"
                    ]:
                        m = re.search(p_regex, content)
                        if m:
                            match_val = m.group(1)
                            break

                    if match_val:
                        is_float = '.' in match_val
                        curr = float(match_val)
                        # Relax (Decrease threshold)
                        new_val = curr * 0.95 if is_float else int(curr - 5)
                        if new_val < 0: new_val = 0

                        if is_float: new_val_str = f"{new_val:.2f}"
                        else: new_val_str = str(int(new_val))

                        new_content, old_val = self._update_param(new_content, param, new_val_str)
                        if old_val:
                            changes.append(f"{param}: {old_val} -> {new_val_str} (Relaxed due to WR {data['wr']:.1f}%)")
                            modified = True

            # 4. Low R:R (< 1.5) -> Tighten Stop
            if data['rr'] < 1.5 and data['wr'] < 90 and not modified:
                 param = 'stop_pct'
                 if param in target_params:
                    match_val = None
                    for p_regex in [
                        rf"self\.{param}\s*=\s*(\d+\.?\d*)",
                        rf"parser\.add_argument\(['\"]--{param}['\"].*default=(\d+\.?\d*)",
                        rf"['\"]{param}['\"]\s*:\s*(\d+\.?\d*)"
                    ]:
                        m = re.search(p_regex, content)
                        if m:
                            match_val = m.group(1)
                            break

                    if match_val:
                        curr = float(match_val)
                        new_val = max(0.5, curr - 0.2)
                        new_val_str = f"{new_val:.1f}"

                        new_content, old_val = self._update_param(new_content, param, new_val_str)
                        if old_val:
                            changes.append(f"{param}: {old_val} -> {new_val_str} (Tightened due to R:R {data['rr']:.2f})")
                            modified = True

            if modified:
                # Add comment
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"

                # Insert comment after imports or docstring
                lines = new_content.split('\n')
                insert_idx = 1
                for i, line in enumerate(lines):
                    if line.startswith('import ') or line.startswith('from '):
                        insert_idx = i
                        break

                lines.insert(insert_idx, comment)
                final_content = '\n'.join(lines)

                with open(filepath, 'w') as f:
                    f.write(final_content)

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
            f.write("| Strategy | Signals | Entries | Wins | WR% | PF | Score | Status |\n")
            f.write("|----------|---------|---------|------|-----|----|-------|--------|\n")
            for name, m in sorted_strategies:
                status = "✓" if m['score'] > 40 else "✗"
                f.write(f"| {name} | {m['signals']} | {m['entries']} | {m['wins']} | {m['wr']:.1f}% | {m['pf']:.1f} | {m['score']:.1f} | {status} |\n")

            f.write("\n🔧 INCREMENTAL IMPROVEMENTS APPLIED:\n")
            if not self.improvements:
                f.write("No improvements applied.\n")
            for item in self.improvements:
                f.write(f"1. {item['strategy']}\n")
                for change in item['changes']:
                    f.write(f"   - {change}\n")

            f.write("\n📊 STRATEGY RANKING (Top 5 for Tomorrow):\n")
            for i, name in enumerate(self.strategies_to_deploy):
                score = self.metrics[name]['score']
                f.write(f"{i+1}. {name} - Score: {score:.1f} - [Action: Start/Restart]\n")

            f.write("\n🚀 DEPLOYMENT PLAN:\n")
            f.write("- Stop: All underperforming strategies\n")
            f.write(f"- Start: {', '.join(self.strategies_to_deploy)}\n")

            f.write("\n⚠️ ISSUES FOUND:\n")
            for name, m in sorted_strategies:
                if m['errors'] > 0:
                    f.write(f"- {name}: {m['errors']} errors detected.\n")

            f.write("\n💡 INSIGHTS FOR TOMORROW:\n")
            f.write("- Monitor strategies with recent parameter changes closely.\n")

        print(f"Report generated: {report_file}")

    def generate_deployment_script(self):
        script_path = os.path.join(REPO_ROOT, 'scripts', 'deploy_daily_optimized.sh')
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated deployment script\n\n")
            f.write("echo 'Stopping all strategies...'\n")
            f.write("pkill -f 'python3 openalgo/strategies/scripts/' || true\n\n")

            f.write("export OPENALGO_APIKEY=${OPENALGO_APIKEY:-'demo_key'}\n\n")

            f.write("echo 'Starting optimized strategies...'\n")
            for strategy in self.strategies_to_deploy:
                # Resolve symbol
                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')

                # Check for args based on strategy name
                args = f"--symbol {symbol}"
                if 'mcx' in strategy:
                    args += " --underlying CRUDEOIL" # Hack/Default

                f.write(f"nohup python3 openalgo/strategies/scripts/{strategy}.py {args} > openalgo/log/strategies/{strategy}_{symbol}.log 2>&1 &\n")
                f.write(f"echo 'Started {strategy}'\n")

            f.write("\necho 'Deployment complete.'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
