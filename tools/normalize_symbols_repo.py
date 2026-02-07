#!/usr/bin/env python3
import os
import sys
import argparse
import re
import json
import pandas as pd
from datetime import datetime
from collections import defaultdict

# Setup paths
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from openalgo.strategies.utils.mcx_utils import MCX_FUZZY_PATTERN, normalize_mcx_string

DATA_DIR = os.path.join(REPO_ROOT, 'openalgo', 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Valid Months
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

def load_instruments():
    if not os.path.exists(INSTRUMENTS_FILE):
        return None
    try:
        df = pd.read_csv(INSTRUMENTS_FILE)
        return set(df['symbol'].unique())
    except Exception as e:
        print(f"Warning: Failed to load instruments: {e}")
        return None

def scan_file(filepath, instruments, strict=False):
    issues = []
    changes_made = False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return "", False, []

    def replacement_handler(match):
        nonlocal changes_made
        original = match.group(0)

        # Validation of Month
        month = match.group(3).upper()
        if month not in MONTHS:
            issues.append({
                "file": filepath,
                "symbol": original,
                "error": f"Invalid month: {month}",
                "status": "INVALID"
            })
            return original

        normalized = normalize_mcx_string(original)

        if instruments is not None:
            if normalized not in instruments:
                 issues.append({
                    "file": filepath,
                    "symbol": original,
                    "normalized": normalized,
                    "error": "Symbol not found in instrument master",
                    "status": "MISSING"
                 })
                 return original

        if original != normalized:
            changes_made = True
            issues.append({
                "file": filepath,
                "symbol": original,
                "normalized": normalized,
                "status": "NORMALIZED"
            })
            return normalized

        return original

    # Apply regex substitution using FUZZY pattern
    new_content = MCX_FUZZY_PATTERN.sub(replacement_handler, content)

    return new_content, changes_made, issues

def main():
    parser = argparse.ArgumentParser(description="Normalize Symbols in Repo")
    parser.add_argument("--write", action="store_true", help="Write changes to files")
    parser.add_argument("--check", action="store_true", help="Check only, don't write")
    parser.add_argument("--strict", action="store_true", help="Fail on invalid symbols")
    args = parser.parse_args()

    instruments = load_instruments()
    if instruments is None:
        if args.strict:
            print("Error: Instrument master missing or unreadable in strict mode.")
            sys.exit(3)
        else:
            print("Warning: Instrument master missing. Validation will be limited.")

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instruments_loaded": instruments is not None,
        "issues": []
    }

    files_to_scan = []
    # Walk openalgo/strategies
    strategies_dir = os.path.join(REPO_ROOT, 'openalgo', 'strategies')
    for root, dirs, files in os.walk(strategies_dir):
        # Exclude tests directories
        if 'tests' in dirs:
            dirs.remove('tests')
        if 'test' in dirs:
            dirs.remove('test')

        for file in files:
            if file.endswith('.py') or file.endswith('.json'):
                files_to_scan.append(os.path.join(root, file))

    for filepath in files_to_scan:
        new_content, changed, file_issues = scan_file(filepath, instruments, args.strict)
        if file_issues:
            audit_report["issues"].extend(file_issues)

        if changed and args.write:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Fixed: {filepath}")
            except Exception as e:
                print(f"Error writing {filepath}: {e}")

    # Generate Reports
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # JSON Report
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.json'), 'w') as f:
        json.dump(audit_report, f, indent=2)

    # Markdown Report
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.md'), 'w') as f:
        f.write("# Symbol Audit Report\n\n")
        f.write(f"Date: {datetime.now()}\n")
        f.write(f"Strict Mode: {args.strict}\n")
        f.write(f"Instruments Loaded: {instruments is not None}\n\n")

        if not audit_report["issues"]:
             f.write("✅ No issues found.\n")
        else:
             f.write("| File | Symbol | Status | Details |\n")
             f.write("|---|---|---|---|\n")
             for issue in audit_report["issues"]:
                 f.write(f"| {os.path.basename(issue['file'])} | {issue['symbol']} | {issue['status']} | {issue.get('error', issue.get('normalized', ''))} |\n")

    # Check for strict failure
    # In strict check mode: fail if ANY issue (NORMALIZED, INVALID, MISSING) exists.
    # Why NORMALIZED? Because "changes that still pass strict validation" is the requirement for Hard-Gate "Normalize produced either (a) no changes or (b) changes that still pass".
    # But here, if we are in check mode, "needing normalization" is technically a failure of validation (it's malformed).

    invalid_or_missing = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING')]
    normalized_needed = [i for i in audit_report["issues"] if i['status'] == 'NORMALIZED']

    if args.strict:
        if args.check:
            # Strictly Check: No invalid, No missing, No normalization needed
            if invalid_or_missing or normalized_needed:
                print(f"❌ Strict Check Failed: {len(invalid_or_missing)} invalid/missing, {len(normalized_needed)} need normalization.")
                sys.exit(1)
        else:
            # Just strict: Fail on Invalid/Missing (Normalization applied if --write)
            if invalid_or_missing:
                print(f"❌ Strict Mode Failed: {len(invalid_or_missing)} invalid/missing symbols.")
                sys.exit(1)

    if invalid_or_missing:
        print(f"⚠️ Found {len(invalid_or_missing)} invalid/missing symbols.")

    if normalized_needed:
        print(f"ℹ️ Found {len(normalized_needed)} symbols needing normalization.")

    if args.write:
         print("✅ Normalization complete.")
    else:
         print("✅ Check complete.")

if __name__ == "__main__":
    main()
