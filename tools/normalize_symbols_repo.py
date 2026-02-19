#!/usr/bin/env python3
import os
import sys
import argparse
import re
import json
import time
import pandas as pd
from datetime import datetime
from collections import defaultdict

# Setup paths
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(REPO_ROOT, 'openalgo', 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Regex for MCX Symbols
# Pattern: SYMBOL + 1-2 digits (Day) + 3 letters (Month) + 2 digits (Year) + FUT
# e.g. GOLDM05FEB26FUT
MCX_PATTERN = re.compile(r'\b([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT\b', re.IGNORECASE)

# Valid Months
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

def check_instruments_freshness():
    if not os.path.exists(INSTRUMENTS_FILE):
        return False, "Instruments file missing"

    mtime = os.path.getmtime(INSTRUMENTS_FILE)
    file_age = time.time() - mtime
    if file_age > 86400: # 24 hours
        return False, f"Instruments file stale ({file_age/3600:.1f} hours old)"

    return True, "Fresh"

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
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return "", False, []

    def replacement_handler(match):
        nonlocal changes_made
        original = match.group(0)
        normalized = normalize_mcx_symbol(match)

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

        # Validation against Instruments
        if instruments is not None:
            if normalized not in instruments:
                 # Check if original was in instruments (unlikely if malformed, but possible)
                 if original in instruments:
                     return original

                 issues.append({
                    "file": filepath,
                    "symbol": original,
                    "normalized": normalized,
                    "error": "Symbol not found in instrument master",
                    "status": "MISSING"
                 })
                 # If we can't find it in master, we count it as MISSING/INVALID
                 # In strict mode, this is an error.
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

    # Check Freshness
    fresh, msg = check_instruments_freshness()

    # Strict Mode Policy: Fail if instruments missing or stale
    if instruments is None or (not fresh and args.strict):
        if args.strict:
            print(f"❌ Error: Instrument master missing/stale in strict mode. Status: {msg}")
            sys.exit(3)
        else:
            print(f"⚠️ Warning: Instrument master missing or stale ({msg}). Validation will be limited.")

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instruments_loaded": instruments is not None,
        "issues": []
    }

    files_to_scan = []
    # Walk openalgo/strategies and other relevant dirs if needed
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
    json_path = os.path.join(REPORTS_DIR, 'symbol_audit.json')
    with open(json_path, 'w') as f:
        json.dump(audit_report, f, indent=2)
    print(f"Report generated: {json_path}")

    # Markdown Report
    md_path = os.path.join(REPORTS_DIR, 'symbol_audit.md')
    with open(md_path, 'w') as f:
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
                 rel_path = os.path.relpath(issue['file'], REPO_ROOT)
                 f.write(f"| {rel_path} | {issue['symbol']} | {issue['status']} | {issue.get('error', issue.get('normalized', ''))} |\n")
    print(f"Report generated: {md_path}")

    # Exit Logic
    invalid_symbols = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING')]
    normalized_needed = [i for i in audit_report["issues"] if i['status'] == 'NORMALIZED']

    if invalid_symbols:
        print(f"❌ Found {len(invalid_symbols)} invalid/missing symbols.")
        if args.strict:
            sys.exit(1) # STRICT FAIL

    if args.check:
         # In check mode, if normalization is needed, it's a failure (files are dirty)
         if normalized_needed:
             print(f"❌ Found {len(normalized_needed)} symbols needing normalization.")
             if args.strict:
                 sys.exit(1)
             # Even in non-strict check, if we found things to normalize, exit 1 usually?
             # But prompt says strict treats warnings as errors.
             # Non-strict check might just report.
             pass

    if args.write:
         print("✅ Normalization complete.")
    elif not invalid_symbols and not normalized_needed:
         print("✅ All symbols valid.")
         sys.exit(0)

if __name__ == "__main__":
    main()
