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
TUNABLE_PARAMS = {
    'supertrend_vwap_strategy': ['threshold', 'stop_pct'],
    'ai_hybrid_reversion_breakout': ['rsi_lower', 'rsi_upper', 'stop_pct'],
    'mcx_commodity_momentum_strategy': ['adx_threshold', 'min_atr'],
    'advanced_ml_momentum_strategy': ['threshold', 'stop_pct'],
    'gap_fade_strategy': ['threshold']
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
            # Need to handle potential extra underscores in strategy name
            parts = filename.replace('.log', '').split('_')

            # Heuristic to find symbol (usually last part, uppercase)
            symbol = parts[-1]
            strategy_name = "_".join(parts[:-1])

            # Ensure strategy exists in TUNABLE_PARAMS or use default
            if strategy_name not in TUNABLE_PARAMS:
                 # Try to find a partial match
                 found = False
                 for k in TUNABLE_PARAMS:
                     if k in strategy_name:
                         strategy_name = k
                         found = True
                         break
                 if not found:
                     logger.warning(f"Strategy {strategy_name} not in tunable params. Using default extraction.")

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
                if "ERROR" in line or "Exception" in line:
                    errors += 1

                # Signal Detection
                if "Signal Detected" in line or "Signal" in line or "Crossover" in line:
                    signals += 1

                # Entry Detection
                if "BUY Order" in line or "SELL Order" in line or "Executing" in line:
                    entries += 1

                # Exit / PnL Detection
                if "PnL:" in line:
                    try:
                        # Extract PnL value
                        # Format: ... PnL: 123.45 ...
                        part = line.split("PnL:")[1].strip().split()[0]
                        val = float(part)
                        total_pnl += val
                        if val > 0:
                            wins += 1
                            gross_win += val
                        else:
                            losses += 1
                            gross_loss += abs(val)
                    except: pass
                elif "Target Hit" in line: # Fallback if PnL not parsed
                     # Only increment if not already counted via PnL
                     pass

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
            # Proxy Sharpe with R:R capped at 3
            sharpe_proxy = min(rr_ratio, 3.0)
            entry_rate = entries / signals if signals > 0 else 0

            # Normalize terms to roughly 0-100 scale for easier reading
            # WR is 0-100.
            # PF: 2.0 is good. Map 0-5 to 0-100? Let's keep it raw weighted.

            # Actually, let's normalize everything to 0-100 contributions
            s_wr = win_rate # 0-100
            s_pf = min(profit_factor, 5.0) * 20 # 5.0 -> 100
            s_sh = sharpe_proxy * 33 # 3.0 -> 99
            s_er = entry_rate * 100 # 0-100
            s_ef = error_free_rate * 100 # 0-100

            score = (s_wr * 0.3) + (s_pf * 0.3) + (s_sh * 0.2) + (s_er * 0.1) + (s_ef * 0.1)

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

    def update_param_in_content(self, content, param, change_func):
        """
        Generic parameter updater.
        Tries:
        1. argparse: parser.add_argument('--param', ... default=VAL)
        2. dict: 'param': VAL (inside simple dicts)
        3. class/var: self.param = VAL or param = VAL
        """
        new_content = content
        change_desc = None

        # 1. Argparse
        # Regex: parser.add_argument\s*\(\s*['"]--param['"]\s*,.*default\s*=\s*(\d+(\.\d*)?)
        argparse_pattern = re.compile(rf"(parser\.add_argument\s*\(\s*['\"]--{param}['\"]\s*,.*?default\s*=\s*)(\d+(\.\d*)?)", re.DOTALL)
        match = argparse_pattern.search(content)
        if match:
            current_val = float(match.group(2))
            new_val = change_func(current_val)
            # Ensure int if original was int (no dot)
            if '.' not in match.group(2):
                new_val = int(new_val)
            else:
                new_val = round(new_val, 2)

            replacement = f"{match.group(1)}{new_val}"
            new_content = content.replace(match.group(0), replacement)
            change_desc = f"{param}: {current_val} -> {new_val}"
            return new_content, change_desc

        # 2. Dictionary key (e.g. PARAMS = { ... 'key': val ... })
        # Regex: 'param'\s*:\s*(\d+(\.\d*)?)
        dict_pattern = re.compile(rf"(['\"]{param}['\"]\s*:\s*)(\d+(\.\d*)?)")
        match = dict_pattern.search(content)
        if match:
            current_val = float(match.group(2))
            new_val = change_func(current_val)
            if '.' not in match.group(2):
                new_val = int(new_val)
            else:
                new_val = round(new_val, 2)

            replacement = f"{match.group(1)}{new_val}"
            new_content = content.replace(match.group(0), replacement)
            change_desc = f"{param}: {current_val} -> {new_val}"
            return new_content, change_desc

        # 3. Class attribute or Variable (self.param = val or param = val)
        # Regex: (self\.)?param\s*=\s*(\d+(\.\d*)?)
        # Be careful not to match inside other words
        var_pattern = re.compile(rf"(^|\s)(self\.)?{param}\s*=\s*(\d+(\.\d*)?)")
        match = var_pattern.search(content)
        if match:
            current_val = float(match.group(3))
            new_val = change_func(current_val)
            if '.' not in match.group(3):
                new_val = int(new_val)
            else:
                new_val = round(new_val, 2)

            # Reconstruct the string
            # group(0) is full match
            # group(1) is prefix space
            # group(2) is 'self.' or None
            # group(3) is val
            prefix = match.group(1)
            self_prefix = match.group(2) if match.group(2) else ""

            replacement = f"{prefix}{self_prefix}{param} = {new_val}"
            new_content = content.replace(match.group(0), replacement)
            change_desc = f"{param}: {current_val} -> {new_val}"
            return new_content, change_desc

        return content, None

    def optimize_strategies(self):
        for strategy_name, data in self.metrics.items():
            # Find the file
            # Map strategy name to filename (metrics keys are normalized)
            # Try appending _strategy.py or just .py
            candidates = [
                os.path.join(STRATEGIES_DIR, f"{strategy_name}.py"),
                os.path.join(STRATEGIES_DIR, f"{strategy_name}_strategy.py")
            ]
            filepath = None
            for c in candidates:
                if os.path.exists(c):
                    filepath = c
                    break

            if not filepath:
                logger.warning(f"Strategy file not found for {strategy_name}")
                continue

            with open(filepath, 'r') as f:
                content = f.read()

            new_content = content
            changes = []

            target_params = TUNABLE_PARAMS.get(strategy_name, [])

            # Optimization Logic

            # 1. High Rejection Rate (> 70%) -> Lower Threshold
            if data['rejection'] > 70:
                for param in target_params:
                    if 'threshold' in param or 'rsi_upper' in param or 'rsi_lower' in param or 'gap' in param:
                        # Logic: Make it easier to enter
                        # If threshold (usually min), decrease it
                        # If rsi_upper (sell zone), maybe lower it to trigger sooner? Or higher?
                        # If Rejection is high, it means signals are generated but filtered.
                        # Usually filters are things like ADX, Min ATR.

                        if 'threshold' in param or 'min_atr' in param:
                            # Decrease by 5%
                            func = lambda x: x * 0.95
                            if 'rsi' in param: func = lambda x: x # RSI logic is complex, skip for simple threshold
                            if 'gap' in param: func = lambda x: x * 0.9 # Lower gap threshold

                            if 'threshold' in param and isinstance(data['rejection'], float):
                                func = lambda x: x - (5 if x > 10 else 0.5)

                            new_content, desc = self.update_param_in_content(new_content, param, func)
                            if desc: changes.append(f"{desc} (High Rejection {data['rejection']:.1f}%)")

                        elif 'rsi_lower' in param:
                            # Relax: Increase RSI Lower (e.g., 30 -> 35)
                            func = lambda x: min(45, x + 5)
                            new_content, desc = self.update_param_in_content(new_content, param, func)
                            if desc: changes.append(f"{desc} (High Rejection {data['rejection']:.1f}%)")

                        elif 'rsi_upper' in param:
                            # Relax: Decrease RSI Upper (e.g., 70 -> 65)
                            func = lambda x: max(55, x - 5)
                            new_content, desc = self.update_param_in_content(new_content, param, func)
                            if desc: changes.append(f"{desc} (High Rejection {data['rejection']:.1f}%)")

            # 2. Low Win Rate (< 60%) -> Tighten Filters
            if data['wr'] < 60:
                for param in target_params:
                    # Tighten RSI (narrow range?), Increase Threshold
                    if 'threshold' in param or 'adx' in param:
                         # Increase by 5%
                         func = lambda x: x + (5 if x > 10 else 1)
                         new_content, desc = self.update_param_in_content(new_content, param, func)
                         if desc: changes.append(f"{desc} (Low WR {data['wr']:.1f}%)")

            # 3. High Win Rate (> 80%) -> Relax Filters
            elif data['wr'] > 80:
                for param in target_params:
                    if 'threshold' in param or 'rsi_lower' in param:
                         # Relax
                         func = lambda x: x - (5 if x > 10 else 0.5)
                         # Special case for RSI Lower: Higher is more relaxed (closer to 50) for oversold?
                         # Typically RSI < 30. Relaxing means RSI < 35. So increase value.
                         if 'rsi_lower' in param:
                             func = lambda x: min(45, x + 5)

                         new_content, desc = self.update_param_in_content(new_content, param, func)
                         if desc: changes.append(f"{desc} (High WR {data['wr']:.1f}%)")

            # 4. Low R:R (< 1.5) -> Tighten Stop
            if data['rr'] < 1.5 and data['wr'] < 90:
                for param in target_params:
                    if 'stop' in param: # stop_pct
                        func = lambda x: max(0.5, x * 0.9) # Reduce stop by 10%
                        new_content, desc = self.update_param_in_content(new_content, param, func)
                        if desc: changes.append(f"{desc} (Low R:R {data['rr']:.2f})")

            if changes:
                # Add comment
                timestamp = datetime.now().strftime("%Y-%m-%d")
                comment = f"\n# [Optimization {timestamp}] Changes: {', '.join(changes)}"

                # Insert comment after docstring
                lines = new_content.split('\n')
                insert_idx = 0
                in_docstring = False
                for i, line in enumerate(lines):
                    if '"""' in line or "'''" in line:
                        if in_docstring:
                            insert_idx = i + 1
                            break
                        else:
                            in_docstring = True
                            if line.count('"""') == 2 or line.count("'''") == 2:
                                insert_idx = i + 1
                                break

                if insert_idx == 0: insert_idx = 2

                lines.insert(insert_idx, comment)
                new_content = '\n'.join(lines)

                with open(filepath, 'w') as f:
                    f.write(new_content)

                self.improvements.append({'strategy': strategy_name, 'changes': changes})
                logger.info(f"Updated {strategy_name}: {changes}")

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
                status = "✓" if m['score'] > 40 else "✗" # Arbitrary threshold
                f.write(f"| {name} | {m['signals']} | {m['entries']} | {m['wins']} | {m['wr']:.1f}% | {m['pf']:.1f} | {m['rr']:.2f} | {m['rejection']:.1f}% | {m['score']:.1f} | {status} |\n")

            f.write("\n## 🔧 INCREMENTAL IMPROVEMENTS APPLIED:\n")
            if not self.improvements:
                f.write("No improvements applied.\n")
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
                # Find the actual filename again
                candidates = [
                    f"{strategy}.py",
                    f"{strategy}_strategy.py"
                ]
                filename = None
                for c in candidates:
                    if os.path.exists(os.path.join(STRATEGIES_DIR, c)):
                        filename = c
                        break

                if not filename: continue

                symbol = self.metrics.get(strategy, {}).get('symbol', 'NIFTY')

                # Construct command
                # Use setsid or nohup
                cmd = f"nohup python3 openalgo/strategies/scripts/{filename} --symbol {symbol} --api_key $OPENALGO_APIKEY > openalgo/log/strategies/{strategy}_{symbol}.log 2>&1 &"
                f.write(f"echo 'Starting {strategy} on {symbol}'\n")
                f.write(f"{cmd}\n")

            f.write("\necho 'Deployment complete.'\n")

        os.chmod(script_path, 0o755)
        print(f"Deployment script generated: {script_path}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.parse_logs()
    opt.optimize_strategies()
    opt.generate_report()
    opt.generate_deployment_script()
