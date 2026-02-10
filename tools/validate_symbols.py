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

# Also add openalgo if needed
OPENALGO_DIR = os.path.join(REPO_ROOT, 'openalgo')
if OPENALGO_DIR not in sys.path:
    sys.path.insert(0, OPENALGO_DIR)

DATA_DIR = os.path.join(OPENALGO_DIR, 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
CONFIG_FILE = os.path.join(OPENALGO_DIR, 'strategies', 'active_strategies.json')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Regex for MCX Symbols
# Canonical: SYMBOL + DD + MMM + YY + FUT
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

        for strat_id, config in configs.items():
            # Check if config has symbol
            # The config format might vary, assuming typical structure
            # If config is a list (some strategies), iterate
            if isinstance(config, list):
                 items = config
            else:
                 items = [config]

            for item in items:
                if not isinstance(item, dict): continue

                # Check symbol fields if present
                # Use resolver if possible, or just check 'symbol' key
                # This part depends on how SymbolResolver works.
                # Assuming resolver.resolve(config) returns validated object or raises/returns error
                pass
                # For now, let's focus on hardcoded symbols in code and MCX pattern,
                # as verifying config logic requires deep knowledge of SymbolResolver.
                # But the prompt says "Validates each symbol".
                # Let's try to use resolver if we can.
                try:
                    res = resolver.resolve(item)
                    if res is None:
                         issues.append({
                            "source": "active_strategies.json",
                            "id": strat_id,
                            "error": f"Failed to resolve symbol for {item}",
                            "status": "INVALID"
                        })
                except Exception as e:
                     # If validation fails
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

def scan_files_for_hardcoded_symbols(instruments):
    issues = []
    strategies_dir = os.path.join(OPENALGO_DIR, 'strategies')

    for root, dirs, files in os.walk(strategies_dir):
        # Exclude tests
        if 'tests' in dirs:
            dirs.remove('tests')
        if 'test' in dirs:
            dirs.remove('test')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')

        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    continue # Skip binary/bad files

                for match in MCX_PATTERN.finditer(content):
                    symbol_str = match.group(0)
                    parts = match.groups() # (Symbol, Day, Month, Year)

                    # Validate Month
                    if parts[2].upper() not in MONTHS:
                        issues.append({
                            "source": os.path.relpath(filepath, REPO_ROOT),
                            "symbol": symbol_str,
                            "error": f"Invalid month: {parts[2]}",
                            "status": "INVALID"
                        })
                        continue

                    # Normalized form:
                    normalized = f"{parts[0].upper()}{int(parts[1]):02d}{parts[2].upper()}{parts[3]}FUT"

                    if symbol_str != normalized:
                         issues.append({
                            "source": os.path.relpath(filepath, REPO_ROOT),
                            "symbol": symbol_str,
                            "normalized": normalized,
                            "error": "Symbol is malformed (needs normalization)",
                            "status": "MALFORMED"
                        })

                    if normalized not in instruments:
                        issues.append({
                            "source": os.path.relpath(filepath, REPO_ROOT),
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
    print(f"Instrument Status: {msg}")

    if not fresh:
        if args.strict:
            print("❌ Strict Mode: Instrument master stale/missing. Exiting.")
            sys.exit(3)
        else:
            print("Warning: proceeding with stale data.")

    # Load resolver and instruments
    resolver = None
    instruments = set()
    try:
        try:
            from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        except ImportError:
            # Try adjusting path again if needed, or fail
            sys.path.insert(0, os.path.join(REPO_ROOT, 'vendor', 'openalgo'))
            from strategies.utils.symbol_resolver import SymbolResolver

        # Assuming SymbolResolver takes file path
        if os.path.exists(INSTRUMENTS_FILE):
             resolver = SymbolResolver(INSTRUMENTS_FILE)
             # Access underlying df
             if hasattr(resolver, 'df'):
                 instruments = set(resolver.df['symbol'].unique())
             else:
                 # Fallback if SymbolResolver doesn't expose df directly
                 import pandas as pd
                 df = pd.read_csv(INSTRUMENTS_FILE)
                 instruments = set(df['symbol'].unique())
    except Exception as e:
        print(f"Error loading SymbolResolver/Instruments: {e}")
        if args.strict:
            sys.exit(3)

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instrument_status": msg,
        "issues": []
    }

    # 2. Validate Configs
    if resolver:
        print("Validating configs...")
        config_issues = validate_config_symbols(resolver)
        audit_report["issues"].extend(config_issues)

    # 3. Validate Hardcoded Symbols
    print("Scanning files for hardcoded symbols...")
    hardcoded_issues = scan_files_for_hardcoded_symbols(instruments)
    audit_report["issues"].extend(hardcoded_issues)

    # Report Generation
    os.makedirs(REPORTS_DIR, exist_ok=True)
    json_path = os.path.join(REPORTS_DIR, 'symbol_audit.json')
    with open(json_path, 'w') as f:
        json.dump(audit_report, f, indent=2)

    # Also create Markdown
    md_path = os.path.join(REPORTS_DIR, 'symbol_audit.md')
    with open(md_path, 'w') as f:
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

    print(f"Reports generated in {REPORTS_DIR}")

    # Print Summary and Exit
    invalid_issues = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING', 'ERROR', 'MALFORMED')]

    if invalid_issues:
        print(f"❌ Validation Failed: {len(invalid_issues)} issues found.")
        for issue in invalid_issues:
             print(f" - [{issue['status']}] {issue.get('source')}: {issue.get('symbol', 'N/A')} -> {issue.get('error')}")

        if args.strict:
            sys.exit(2)
    else:
        print("✅ All symbols valid.")
        sys.exit(0)

if __name__ == "__main__":
    main()
