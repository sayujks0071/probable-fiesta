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

DATA_DIR = os.path.join(REPO_ROOT, 'openalgo', 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Import mcx_utils
try:
    from openalgo.strategies.utils.mcx_utils import normalize_mcx_string
except ImportError:
    # Fallback path fix
    sys.path.insert(0, os.path.join(REPO_ROOT, 'openalgo'))
    from strategies.utils.mcx_utils import normalize_mcx_string

# Regex for MCX Symbols - Using similar pattern as mcx_utils but ensuring word boundary
MCX_PATTERN = re.compile(r'\b([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT\b', re.IGNORECASE)

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

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        # Skip binary or unreadable files
        return "", False, []

    def replacement_handler(match):
        nonlocal changes_made
        original = match.group(0)

        # Use centralized normalization logic
        try:
            normalized = normalize_mcx_string(original)
        except Exception:
            normalized = original

        # Validation checks
        month = match.group(3).upper()
        # Basic month validation (already implied by normalize logic usually, but good to be explicit)
        valid_months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        if month not in valid_months:
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

                 issues.append({
                    "file": filepath,
                    "symbol": original,
                    "normalized": normalized,
                    "error": "Symbol not found in instrument master",
                    "status": "MISSING"
                 })
                 # Even if missing, we might want to normalize format?
                 # Strict mode says: "If it can’t be validated from instrument master, it is an error."
                 # So we log it as MISSING.
                 # If we return normalized, we might be introducing a "correctly formatted" but "invalid" symbol.
                 # But usually we want canonical format.
                 # Let's normalize it so at least format is correct, but flag it as MISSING.
                 if original != normalized:
                     changes_made = True
                 return normalized

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
        msg = "Instrument master missing or unreadable."
        print(f"Warning: {msg}")
        if args.strict:
            print("Error: Strict mode requires instrument master.")
            sys.exit(3)

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instruments_loaded": instruments is not None,
        "issues": []
    }

    files_to_scan = []
    # Walk openalgo/strategies and other relevant dirs
    # User mentioned: "tools/validate_symbols.py Scans: a) all Python strategy files b) configs..."
    # normalize_symbols_repo usually targets source code.

    scan_dirs = [
        os.path.join(REPO_ROOT, 'openalgo', 'strategies'),
        os.path.join(REPO_ROOT, 'tools') # Maybe tools themselves have symbols?
    ]

    for start_dir in scan_dirs:
        for root, dirs, files in os.walk(start_dir):
            # Exclude tests directories
            if 'tests' in dirs:
                dirs.remove('tests')
            if 'test' in dirs:
                dirs.remove('test')

            # Exclude virtual envs or hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                if file.endswith('.py') or file.endswith('.json'):
                    files_to_scan.append(os.path.join(root, file))

    print(f"Scanning {len(files_to_scan)} files...")

    for filepath in files_to_scan:
        new_content, changed, file_issues = scan_file(filepath, instruments, args.strict)
        if file_issues:
            # Add relative path for cleaner report
            for issue in file_issues:
                issue['file'] = os.path.relpath(issue['file'], REPO_ROOT)
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
                 detail = issue.get('error') or issue.get('normalized') or ''
                 f.write(f"| {issue['file']} | {issue['symbol']} | {issue['status']} | {detail} |\n")
    print(f"Report generated: {md_path}")

    # Check for strict failure
    invalid_symbols = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING')]
    normalized_needed = [i for i in audit_report["issues"] if i['status'] == 'NORMALIZED']

    if invalid_symbols:
        print(f"❌ Found {len(invalid_symbols)} invalid/missing symbols.")
        if args.strict:
            sys.exit(1)

    if args.check:
         if normalized_needed:
             print(f"❌ Found {len(normalized_needed)} symbols needing normalization.")
             if args.strict:
                 sys.exit(1)

    if not invalid_symbols and not normalized_needed:
        print("✅ All symbols valid and normalized.")

if __name__ == "__main__":
    main()
