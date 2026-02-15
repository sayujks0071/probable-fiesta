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

def check_instruments_freshness():
    if not os.path.exists(INSTRUMENTS_FILE):
        return False, "Instruments file missing"

    mtime = os.path.getmtime(INSTRUMENTS_FILE)
    file_age = time.time() - mtime
    if file_age > 86400: # 24 hours
        return False, f"Instruments file stale ({file_age/3600:.1f} hours old)"

    return True, "Fresh"

def load_resolver():
    try:
        # Ensure openalgo is importable
        # Depending on structure, might need:
        # sys.path.insert(0, REPO_ROOT)
        from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        return SymbolResolver(INSTRUMENTS_FILE)
    except Exception as e:
        print(f"Warning: Failed to load SymbolResolver: {e}")
        return None

def validate_config_symbols(resolver):
    issues = []
    if not os.path.exists(CONFIG_FILE):
        return issues # No config to validate

    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
            if not content.strip():
                return issues
            configs = json.loads(content)

        # Configs can be a dict of strategy_id -> config
        # or list? Usually dict in active_strategies.json

        if not isinstance(configs, dict):
             # Try list if format changed?
             return issues

        for strat_id, config in configs.items():
            try:
                # Resolve returns symbol string or dict (for options) or None
                resolved = resolver.resolve(config)

                if resolved is None:
                    issues.append({
                        "source": "active_strategies.json",
                        "id": strat_id,
                        "error": "Failed to resolve symbol configuration",
                        "status": "INVALID"
                    })
                elif isinstance(resolved, dict):
                    if resolved.get('status') != 'valid':
                        issues.append({
                            "source": "active_strategies.json",
                            "id": strat_id,
                            "error": f"Invalid option configuration: {resolved}",
                            "status": "INVALID"
                        })
                # If resolved is string, it found a symbol. We assume it's valid if resolve returned it.
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
            "error": f"Failed to parse config: {e}",
            "status": "ERROR"
        })
    return issues

def scan_files_for_hardcoded_symbols(instruments):
    issues = []
    strategies_dir = os.path.join(REPO_ROOT, 'openalgo', 'strategies')

    files_to_scan = []
    for root, dirs, files in os.walk(strategies_dir):
        if 'tests' in dirs: dirs.remove('tests')
        if 'test' in dirs: dirs.remove('test')
        if '__pycache__' in dirs: dirs.remove('__pycache__')

        for file in files:
            if file.endswith('.py'):
                files_to_scan.append(os.path.join(root, file))

    for filepath in files_to_scan:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            continue

        for match in MCX_PATTERN.finditer(content):
            symbol_str = match.group(0)
            parts = match.groups() # (Symbol, Day, Month, Year)

            # Validate Month
            if parts[2].upper() not in MONTHS:
                issues.append({
                    "source": os.path.basename(filepath),
                    "symbol": symbol_str,
                    "error": f"Invalid month: {parts[2]}",
                    "status": "INVALID"
                })
                continue

            # Check Normalization
            normalized = f"{parts[0].upper()}{int(parts[1]):02d}{parts[2].upper()}{parts[3]}FUT"

            if symbol_str != normalized:
                 issues.append({
                    "source": os.path.basename(filepath),
                    "symbol": symbol_str,
                    "normalized": normalized,
                    "error": "Symbol is malformed (needs normalization)",
                    "status": "MALFORMED"
                })

            # Check Existence
            if instruments:
                if normalized not in instruments:
                     issues.append({
                        "source": os.path.basename(filepath),
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
        if args.strict:
            sys.exit(3)
        print("Warning: proceeding with stale data.")
    else:
        print(f"✅ Instrument Check Passed: {msg}")

    # Load resolver and instruments
    resolver = load_resolver()
    instruments = set()
    if resolver and not resolver.df.empty:
        instruments = set(resolver.df['symbol'].unique())

    if not instruments:
        print("Warning: No instruments loaded. Validation will fail/warn.")
        if args.strict:
             print("Error: Strict mode requires valid instruments master.")
             sys.exit(3)

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instrument_status": msg,
        "issues": []
    }

    # 2. Validate Configs
    if resolver:
        print("Validating active_strategies.json...")
        config_issues = validate_config_symbols(resolver)
        audit_report["issues"].extend(config_issues)

    # 3. Validate Hardcoded Symbols
    print("Scanning strategy files...")
    hardcoded_issues = scan_files_for_hardcoded_symbols(instruments)
    audit_report["issues"].extend(hardcoded_issues)

    # Report Generation
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.json'), 'w') as f:
        json.dump(audit_report, f, indent=2)

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

    # Summary
    invalid_issues = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING', 'ERROR', 'MALFORMED')]

    if invalid_issues:
        print(f"❌ Validation Failed: {len(invalid_issues)} issues found.")
        for issue in invalid_issues:
             src = issue.get('source', 'Unknown')
             sym = issue.get('symbol', issue.get('id', '-'))
             err = issue.get('error', '')
             print(f" - [{issue['status']}] {src}: {sym} -> {err}")

        if args.strict:
            sys.exit(2)
    else:
        print("✅ All symbols valid.")
        sys.exit(0)

if __name__ == "__main__":
    main()
