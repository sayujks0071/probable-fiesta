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

try:
    from openalgo.strategies.utils.mcx_utils import normalize_mcx_string
except ImportError:
    print("Error: Could not import openalgo.strategies.utils.mcx_utils")
    sys.exit(1)

DATA_DIR = os.path.join(REPO_ROOT, 'openalgo', 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Regex for MCX Symbols
# Pattern: SYMBOL + 1-2 digits (Day) + 3 letters (Month) + 2 digits (Year) + FUT
# e.g. GOLDM05FEB26FUT
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

def scan_file(filepath, instruments, strict=False):
    issues = []
    normalized_content = ""
    changes_made = False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    def replacement_handler(match):
        nonlocal changes_made
        original = match.group(0)

        # Use centralized normalization logic
        normalized = normalize_mcx_string(original)

        # Basic Validation of components from regex match (for reporting)
        # normalize_mcx_string handles the format, but let's check month validity explicitly for reporting
        month = match.group(3).upper()
        if month not in MONTHS:
            issues.append({
                "file": filepath,
                "symbol": original,
                "error": f"Invalid month: {month}",
                "status": "INVALID"
            })
            return original

        if instruments is not None:
            if normalized not in instruments:
                 # Check if original was in instruments (maybe current format is valid?)
                 if original in instruments:
                     return original

                 # Strict check: if normalized version is not in instruments, it's missing/invalid
                 issues.append({
                    "file": filepath,
                    "symbol": original,
                    "normalized": normalized,
                    "error": "Symbol not found in instrument master",
                    "status": "MISSING"
                 })
                 # If valid format but missing in master, we keep original but flag it
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
    if os.path.exists(strategies_dir):
        for root, dirs, files in os.walk(strategies_dir):
            # Exclude tests directories
            if 'tests' in dirs:
                dirs.remove('tests')
            if 'test' in dirs:
                dirs.remove('test')

            # Exclude __pycache__
            if '__pycache__' in dirs:
                dirs.remove('__pycache__')

            for file in files:
                if file.endswith('.py') or file.endswith('.json'):
                    files_to_scan.append(os.path.join(root, file))

    # Scan active_strategies.json specifically if it's not in strategies dir walk
    active_strategies = os.path.join(REPO_ROOT, 'openalgo', 'strategies', 'active_strategies.json')
    if active_strategies not in files_to_scan and os.path.exists(active_strategies):
        files_to_scan.append(active_strategies)


    for filepath in files_to_scan:
        try:
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
        except Exception as e:
            print(f"Error scanning {filepath}: {e}")

    # Generate Reports
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # JSON Report
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.json'), 'w') as f:
        json.dump(audit_report, f, indent=2)

    # Markdown Report
    with open(os.path.join(REPORTS_DIR, 'symbol_audit.md'), 'w') as f:
        f.write("# Symbol Audit Report\n\n")
        f.write(f"Date: {datetime.now()}\n\n")
        f.write(f"Strict Mode: {args.strict}\n\n")
        f.write(f"Instruments Loaded: {instruments is not None}\n\n")

        if not audit_report["issues"]:
             f.write("✅ No issues found.\n")
        else:
             f.write("| File | Symbol | Status | Details |\n")
             f.write("|---|---|---|---|\n")
             for issue in audit_report["issues"]:
                 f.write(f"| {os.path.basename(issue['file'])} | {issue['symbol']} | {issue['status']} | {issue.get('error', issue.get('normalized', ''))} |\n")

    # Check for strict failure
    invalid_symbols = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING')]
    normalized_symbols = [i for i in audit_report["issues"] if i['status'] == 'NORMALIZED']

    if args.strict:
        # Strict mode: Fail on INVALID, MISSING
        if invalid_symbols:
            print(f"❌ Found {len(invalid_symbols)} invalid/missing symbols.")
            sys.exit(1)

        # Strict Check mode: Fail on NORMALIZED too (means codebase is not normalized)
        if args.check and normalized_symbols:
             print(f"❌ Found {len(normalized_symbols)} symbols needing normalization.")
             sys.exit(1)

    if invalid_symbols:
        print(f"❌ Found {len(invalid_symbols)} invalid/missing symbols.")
        # Non-strict mode, we typically just warn, but if we are in 'check' mode maybe we should exit non-zero?
        # The prompt says: "--check (no edits; just validate)".
        # And "--strict (treat warnings as errors; exit non-zero ...)"
        # So without strict, we exit 0 even if issues found, unless the user expects otherwise.
        # But for 'check', usually non-zero exit is expected on issues.
        # However, following strict flag logic strictly: if strict is NOT set, we don't exit non-zero.

    if args.write:
         print("✅ Normalization complete.")
    else:
         print("✅ Check complete.")

if __name__ == "__main__":
    main()
