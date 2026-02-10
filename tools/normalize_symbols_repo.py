#!/usr/bin/env python3
import os
import sys
import argparse
import re
import json
import pandas as pd
from datetime import datetime

# Setup paths
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Also add openalgo if needed
OPENALGO_DIR = os.path.join(REPO_ROOT, 'openalgo')
if OPENALGO_DIR not in sys.path:
    sys.path.insert(0, OPENALGO_DIR)

DATA_DIR = os.path.join(OPENALGO_DIR, 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Regex for MCX Symbols
# Pattern: SYMBOL + 1-2 digits (Day) + 3 letters (Month) + 2 digits (Year) + FUT
# e.g. GOLDM05FEB26FUT
# Capture groups: 1=Symbol, 2=Day, 3=Month, 4=Year
MCX_PATTERN = re.compile(r'\b([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT\b', re.IGNORECASE)

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

def normalize_mcx_symbol(match):
    symbol = match.group(1).upper()
    day = int(match.group(2))
    month = match.group(3).upper()
    year = match.group(4)

    # Normalize: Pad day with 0 if needed
    normalized = f"{symbol}{day:02d}{month}{year}FUT"
    return normalized

def scan_file(filepath, instruments, strict=False):
    issues = []
    normalized_content = ""
    changes_made = False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return "", False, []

    def replacement_handler(match):
        nonlocal changes_made
        original = match.group(0)

        # Validation
        month = match.group(3).upper()
        if month not in MONTHS:
            issues.append({
                "file": os.path.relpath(filepath, REPO_ROOT),
                "symbol": original,
                "error": f"Invalid month: {month}",
                "status": "INVALID"
            })
            return original

        normalized = normalize_mcx_symbol(match)

        if instruments is not None:
            if normalized not in instruments:
                 # Check if original was in instruments (maybe current format is valid?)
                 if original in instruments:
                     return original

                 issues.append({
                    "file": os.path.relpath(filepath, REPO_ROOT),
                    "symbol": original,
                    "normalized": normalized,
                    "error": "Symbol not found in instrument master",
                    "status": "MISSING"
                 })
                 # If missing, we still normalize format if needed, but flag it
                 pass

        if original != normalized:
            changes_made = True
            issues.append({
                "file": os.path.relpath(filepath, REPO_ROOT),
                "symbol": original,
                "normalized": normalized,
                "status": "NORMALIZED"
            })
            return normalized

        return original

    # Apply regex substitution
    new_content = MCX_PATTERN.sub(replacement_handler, content)

    return new_content, changes_made, issues

def main():
    parser = argparse.ArgumentParser(description="Normalize Symbols in Repo")
    parser.add_argument("--write", action="store_true", help="Write changes to files")
    parser.add_argument("--check", action="store_true", help="Check only, don't write")
    parser.add_argument("--strict", action="store_true", help="Fail on invalid symbols")
    args = parser.parse_args()

    instruments = load_instruments()
    msg = "Loaded" if instruments is not None else "Missing/Failed"

    if instruments is None:
        if args.strict:
            print("❌ Strict Mode: Instrument master missing or unreadable.")
            sys.exit(3)
        else:
            print("Warning: Instrument master missing. Validation will be limited.")

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instrument_status": msg,
        "issues": []
    }

    files_to_scan = []
    # Walk openalgo/strategies
    strategies_dir = os.path.join(OPENALGO_DIR, 'strategies')
    for root, dirs, files in os.walk(strategies_dir):
        # Exclude tests directories
        if 'tests' in dirs:
            dirs.remove('tests')
        if 'test' in dirs:
            dirs.remove('test')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')

        for file in files:
            if file.endswith('.py') or file.endswith('.json'):
                files_to_scan.append(os.path.join(root, file))


    print(f"Scanning {len(files_to_scan)} files...")

    for filepath in files_to_scan:
        new_content, changed, file_issues = scan_file(filepath, instruments, args.strict)
        if file_issues:
            audit_report["issues"].extend(file_issues)

        if changed and args.write:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Fixed: {os.path.relpath(filepath, REPO_ROOT)}")
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
        f.write(f"Instrument Status: {msg}\n\n")

        if not audit_report["issues"]:
             f.write("✅ No issues found.\n")
        else:
             f.write("| File | Symbol | Status | Details |\n")
             f.write("|---|---|---|---|\n")
             for issue in audit_report["issues"]:
                 error = issue.get('error', '')
                 normalized = issue.get('normalized', '')
                 details = f"{error} {('(Normalized: ' + normalized + ')') if normalized else ''}"
                 f.write(f"| {issue.get('file')} | {issue.get('symbol')} | {issue['status']} | {details} |\n")

    print(f"Reports generated in {REPORTS_DIR}")

    # Check for strict failure
    invalid_symbols = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING')]
    normalized_needed = [i for i in audit_report["issues"] if i['status'] == 'NORMALIZED']

    if invalid_symbols:
        print(f"❌ Found {len(invalid_symbols)} invalid/missing symbols.")
        for issue in invalid_symbols:
            print(f" - {issue['file']}: {issue['symbol']} [{issue['status']}] {issue.get('error','')}")

        if args.strict:
            sys.exit(1)

    if args.strict and args.check:
         # In strict check mode, fail if normalization is needed
         if normalized_needed:
             print(f"❌ Found {len(normalized_needed)} symbols needing normalization.")
             sys.exit(1)

    if args.write:
         print("✅ Normalization complete.")
    else:
         print("✅ Check complete.")

    sys.exit(0)

if __name__ == "__main__":
    main()
