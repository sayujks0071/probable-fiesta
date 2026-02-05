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
    'orb': ['range_minutes', 'stop_loss_pct'],
    'gap_fade': ['threshold'],
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
        logger.info(f"Found {len(log_files)} log files.")

        for log_file in log_files:
            filename = os.path.basename(log_file)
            # Assuming filename format: strategy_name_SYMBOL.log
            # Handle cases where strategy name has underscores
            parts = filename.replace('.log', '').split('_')
            # Heuristic: Symbol is usually the last part, usually uppercase
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

                # Entry Detection
                if "BUY" in line or "SELL" in line:
                    # Count as entry if it looks like an execution or update,
                    # but try to avoid counting just 'Signal: BUY' if that's counted as signal
                    if "Order" in line or "Executed" in line or "Filled" in line or "Position" in line:
                        entries += 1
                    elif "Signal" in line or "Crossover" in line:
                         # Legacy support: if the log only has "Signal: BUY" to denote entry
                         entries += 1

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        val = float(line.split("PnL:")[1].strip().split()[0])
                        total_pnl += val
                        if val > 0:
                            wins += 1
                            gross_win += val
                        else:
                            losses += 1
                            gross_loss += abs(val)
                    except: pass
                elif "Trailing Stop Hit" in line:
                    wins += 1
                    gross_win += 100

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
            sharpe_proxy = min(rr_ratio, 3.0) # Cap at 3
            score = (win_rate * 0.3) + (min(profit_factor, 10) * 10 * 0.3) + (sharpe_proxy * 20 * 0.2) + ((entries/signals if signals else 0) * 100 * 0.1) + (error_free_rate * 100 * 0.1)

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

    def _update_param_in_content(self, content, param, change_func):
        """
        Helper to find and update a parameter in content using regex.
        Supports: self.param = X, parser default=X, dict key: X
        """
        new_content = content
        change_desc = None

        # 1. Try 'self.param = val'
        pattern_self = fr"(self\.{param}\s*=\s*)(\d+\.?\d*)"
        match = re.search(pattern_self, content)
        if match:
            current_val = float(match.group(2))
            new_val = change_func(current_val)
            # Preserve int if original was int
            if '.' not in match.group(2):
                new_val = int(new_val)

            new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
            change_desc = f"{param}: {current_val} -> {new_val}"
            return new_content, change_desc

        # 2. Try 'parser.add_argument... --param ... default=val'
        # Note: arg name might match param name exactly or be related
        pattern_arg = fr"(parser\.add_argument\(['\"]--{param}['\"].*default=)(\d+\.?\d*)"
        match = re.search(pattern_arg, content)
        if match:
            current_val = float(match.group(2))
            new_val = change_func(current_val)
            if '.' not in match.group(2):
                new_val = int(new_val)

            new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
            change_desc = f"{param}: {current_val} -> {new_val}"
            return new_content, change_desc

        # 3. Try dict key 'param': val (common in PARAMS = { ... })
        pattern_dict = fr"('{param}'\s*:\s*)(\d+\.?\d*)"
        match = re.search(pattern_dict, content)
        if match:
            current_val = float(match.group(2))
            new_val = change_func(current_val)
            if '.' not in match.group(2):
                new_val = int(new_val)

            new_content = new_content.replace(match.group(0), f"{match.group(1)}{new_val}")
            change_desc = f"{param}: {current_val} -> {new_val}"
            return new_content, change_desc

        return new_content, None

    def optimize_strategies(self):
        for strategy, data in self.metrics.items():
            filepath = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            if not os.path.exists(filepath):
                # Try adding _strategy suffix if missing
                filepath_suffix = os.path.join(STRATEGIES_DIR, f"{strategy}_strategy.py")
                if os.path.exists(filepath_suffix):
                    filepath = filepath_suffix
                else:
                    logger.warning(f"Strategy file not found: {filepath}")
                    continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            modified = False
            changes = []

            # Determine tunable params for this strategy
            target_params = TUNABLE_PARAMS.get('default', [])
            # Find best match key in TUNABLE_PARAMS
            for key in TUNABLE_PARAMS:
                if key in strategy:
                    target_params = TUNABLE_PARAMS[key]
                    break

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                param_to_tune = 'threshold' # Default
                if 'gap_fade' in strategy: param_to_tune = 'threshold'

                if param_to_tune in target_params:
                    # Decrease by 5 (or 2 if small)
                    def decrease_func(val):
                        if val < 5: return max(0.1, val - 0.2) # Small float vals
                        return max(0, val - 5)

                    new_content, desc = self._update_param_in_content(new_content, param_to_tune, decrease_func)
                    if desc:
                        changes.append(f"{desc} (Lowered due to Rejection {data['rejection']:.1f}%)")
                        modified = True

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                # Prioritize specific params
                params_to_tighten = []
                if 'rsi_lower' in target_params: params_to_tighten.append('rsi_lower')
                if 'threshold' in target_params: params_to_tighten.append('threshold')

                for param in params_to_tighten:
                    if modified: break # One change per run usually enough? Let's do multiple if needed.

                    def tighten_func(val):
                        # Context dependent.
                        # RSI Lower: Lowering it is tightening (harder to hit < 25 than < 30)
                        if 'rsi_lower' in param: return max(10, val - 5)
                        # Threshold: Increasing it is tightening (usually)
                        if 'threshold' in param: return val + 5
                        return val

                    new_content, desc = self._update_param_in_content(new_content, param, tighten_func)
                    if desc:
                         changes.append(f"{desc} (Tightened due to WR {data['wr']:.1f}%)")
                         modified = True

            # 3. High Win Rate (> 80%) -> Relax Filters (e.g. Gap Fade)
            elif data['wr'] > 80:
                params_to_relax = []
                if 'rsi_lower' in target_params: params_to_relax.append('rsi_lower')
                if 'threshold' in target_params: params_to_relax.append('threshold') # e.g. Gap Fade threshold: Lower = stricter?
                # Wait, Gap Fade: Threshold is min gap size. If gap > threshold, we trade.
                # So decreasing threshold means we trade smaller gaps -> More trades -> Relaxing entry.
                # Correct.

                for param in params_to_relax:
                     def relax_func(val):
                        if 'rsi_lower' in param: return min(40, val + 5)
                        if 'threshold' in param:
                            if val < 5: return max(0.1, val - 0.1) # Gap Fade small float
                            return max(0, val - 5)
                        return val

                     new_content, desc = self._update_param_in_content(new_content, param, relax_func)
                     if desc:
                         changes.append(f"{desc} (Relaxed due to WR {data['wr']:.1f}%)")
                         modified = True

            # 4. Low R:R (< 1.5) or Low Profit Factor -> Tighten Risk or Filters
            if (data['rr'] < 1.0 or data['pf'] < 1.5) and data['wr'] < 80:
                # Tune ADX (Momentum) or Stop Loss
                params_to_tune = []
                if 'adx_threshold' in target_params: params_to_tune.append('adx_threshold')
                if 'stop_pct' in target_params: params_to_tune.append('stop_pct')

                for param in params_to_tune:
                    def optimize_risk(val):
                        if 'adx_threshold' in param: return val + 2 # Higher ADX = Stronger trend requirement
                        if 'stop_pct' in param: return max(0.5, val - 0.2) # Tighter stop
                        return val

                    new_content, desc = self._update_param_in_content(new_content, param, optimize_risk)
                    if desc:
                        changes.append(f"{desc} (Optimized due to R:R {data['rr']:.2f})")
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
