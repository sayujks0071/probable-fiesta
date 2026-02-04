#!/usr/bin/env python3
import os
import sys
import argparse
import time
import json
import re
from datetime import datetime, timedelta

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DATA_DIR = os.path.join(REPO_ROOT, 'openalgo', 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
CONFIG_FILE = os.path.join(REPO_ROOT, 'openalgo', 'strategies', 'active_strategies.json')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Regex for MCX Symbols
MCX_PATTERN = re.compile(r'\b([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT\b', re.IGNORECASE)
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

try:
    from openalgo.strategies.utils.mcx_utils import normalize_mcx_string
except ImportError:
    # Fallback if import fails (though repo root is in path)
    def normalize_mcx_string(s):
        match = MCX_PATTERN.match(s)
        if match:
             return f"{match.group(1).upper()}{int(match.group(2)):02d}{match.group(3).upper()}{match.group(4)}FUT"
        return s

def check_instruments_freshness():
    if not os.path.exists(INSTRUMENTS_FILE):
        return False, "Instruments file missing"

    mtime = os.path.getmtime(INSTRUMENTS_FILE)
    file_age = time.time() - mtime
    if file_age > 86400: # 24 hours
        return False, f"Instruments file stale ({file_age/3600:.1f} hours old)"

    return True, "Fresh"

def validate_strategy_config(resolver):
    issues = []
    if not os.path.exists(CONFIG_FILE):
        return issues

    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
            if not content.strip():
                return issues
            configs = json.loads(content)

        for strat_id, config in configs.items():
            try:
                resolved = resolver.resolve(config)
                if resolved is None:
                    issues.append({
                        "source": "active_strategies.json",
                        "id": strat_id,
                        "error": "Failed to resolve symbol",
                        "status": "INVALID"
                    })
                elif isinstance(resolved, dict):
                    if resolved.get('status') != 'valid':
                        issues.append({
                            "source": "active_strategies.json",
                            "id": strat_id,
                            "error": "Invalid option configuration",
                            "status": "INVALID"
                        })
            except Exception as e:
                issues.append({
                    "source": "active_strategies.json",
                    "id": strat_id,
                    "error": str(e),
                    "status": "ERROR"
                })
    except Exception as e:
        issues.append({
            "source": "active_strategies.json",
            "error": str(e),
            "status": "ERROR"
        })
    return issues

def scan_directory(directory, instruments):
    issues = []
    if not os.path.exists(directory):
        return issues

    for root, dirs, files in os.walk(directory):
        # Exclude tests
        if 'tests' in dirs: dirs.remove('tests')
        if 'test' in dirs: dirs.remove('test')
        if '__pycache__' in dirs: dirs.remove('__pycache__')

        for file in files:
            if file.endswith(('.py', '.json', '.yaml', '.yml')):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, REPO_ROOT)

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    continue # Skip binary/bad files
                except Exception:
                    continue

                for match in MCX_PATTERN.finditer(content):
                    symbol_str = match.group(0)
                    parts = match.groups() # (Symbol, Day, Month, Year)

                    # Validate Month
                    if parts[2].upper() not in MONTHS:
                        issues.append({
                            "source": rel_path,
                            "symbol": symbol_str,
                            "error": f"Invalid month: {parts[2]}",
                            "status": "INVALID"
                        })
                        continue

                    # Normalized form:
                    normalized = normalize_mcx_string(symbol_str)

                    if symbol_str != normalized:
                         issues.append({
                            "source": rel_path,
                            "symbol": symbol_str,
                            "normalized": normalized,
                            "error": "Symbol is malformed (needs normalization)",
                            "status": "MALFORMED"
                        })

                    if normalized not in instruments:
                        issues.append({
                            "source": rel_path,
                            "symbol": symbol_str,
                            "normalized": normalized,
                            "error": "Symbol not found in master",
                            "status": "MISSING"
                        })
    return issues

def main():
    parser = argparse.ArgumentParser(description="Validate Symbols Repo-Level")
    parser.add_argument("--check", action="store_true", help="Run validation")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on failure")
    args = parser.parse_args()

    # 1. Check Freshness
    fresh, msg = check_instruments_freshness()
    if not fresh:
        print(f"❌ Instrument Check Failed: {msg}")
        # In strict mode, fail with code 3
        if args.strict:
            sys.exit(3)
        else:
            print("Warning: proceeding with stale data.")

    # Load resolver
    try:
        # Check if openalgo package is importable
        try:
            from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        except ImportError:
            sys.path.insert(0, os.path.join(REPO_ROOT, 'openalgo'))
            from strategies.utils.symbol_resolver import SymbolResolver

        resolver = SymbolResolver(INSTRUMENTS_FILE)
        instruments = set(resolver.df['symbol'].unique()) if not resolver.df.empty else set()
    except Exception as e:
        print(f"Error loading SymbolResolver: {e}")
        if args.strict:
            sys.exit(3)
        resolver = None
        instruments = set()

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instrument_status": msg,
        "issues": []
    }

    # 2. Validate Active Strategies Config
    if resolver:
        config_issues = validate_strategy_config(resolver)
        audit_report["issues"].extend(config_issues)

    # 3. Validate Hardcoded Symbols in Directories
    dirs_to_scan = [
        os.path.join(REPO_ROOT, 'openalgo', 'strategies'),
        os.path.join(REPO_ROOT, 'openalgo', 'configs'),
        os.path.join(REPO_ROOT, 'configs')
    ]

    for d in dirs_to_scan:
        issues = scan_directory(d, instruments)
        audit_report["issues"].extend(issues)

    # Report Generation
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.json'), 'w') as f:
        json.dump(audit_report, f, indent=2)

    # Also create Markdown
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.md'), 'w') as f:
         f.write("# Symbol Validation Report\n\n")
         f.write(f"Date: {datetime.now()}\n")
         f.write(f"Strict Mode: {args.strict}\n")
         f.write(f"Instrument Status: {msg}\n\n")

         if not audit_report["issues"]:
              f.write("✅ All symbols valid.\n")
         else:
              f.write("| Source | Symbol/ID | Status | Error |\n")
              f.write("|---|---|---|---|\n")
              for issue in audit_report["issues"]:
                  f.write(f"| {issue.get('source')} | {issue.get('symbol', issue.get('id', '-'))} | {issue['status']} | {issue.get('error')} |\n")


    # Print Summary
    invalid_count = len([i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING', 'ERROR', 'MALFORMED')])

    if invalid_count > 0:
        print(f"❌ Validation Failed: {invalid_count} issues found.")
        for issue in audit_report["issues"]:
            print(f" - [{issue['status']}] {issue.get('source')}: {issue.get('symbol', issue.get('id', 'Unknown'))} -> {issue.get('error')}")

        if args.strict:
            sys.exit(2)
    else:
        print("✅ All symbols valid.")
        sys.exit(0)

if __name__ == "__main__":
    main()
