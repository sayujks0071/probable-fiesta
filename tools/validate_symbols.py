#!/usr/bin/env python3
import os
import sys
import argparse
import time
import json
import re
from datetime import datetime, timedelta

# Setup paths
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DATA_DIR = os.path.join(REPO_ROOT, 'openalgo', 'data')
INSTRUMENTS_FILE = os.path.join(DATA_DIR, 'instruments.csv')
ACTIVE_STRATEGIES_FILE = os.path.join(REPO_ROOT, 'openalgo', 'strategies', 'active_strategies.json')
REPORTS_DIR = os.path.join(REPO_ROOT, 'reports')

# Regex for MCX Symbols
MCX_PATTERN = re.compile(r'\b([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT\b', re.IGNORECASE)
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

def check_instruments_freshness(strict=False):
    if not os.path.exists(INSTRUMENTS_FILE):
        return False, "Instruments file missing"

    mtime = os.path.getmtime(INSTRUMENTS_FILE)
    file_age = time.time() - mtime
    if file_age > 86400: # 24 hours
        return False, f"Instruments file stale ({file_age/3600:.1f} hours old)"

    return True, "Fresh"

def validate_config_symbols(resolver):
    issues = []
    if not os.path.exists(ACTIVE_STRATEGIES_FILE):
        # Not an error if file doesn't exist, just nothing to validate
        return issues

    try:
        with open(ACTIVE_STRATEGIES_FILE, 'r') as f:
            content = f.read()
            if not content.strip():
                return issues
            configs = json.loads(content)

        if not isinstance(configs, dict):
             return issues

        for strat_id, config in configs.items():
            try:
                # Mock resolve for validation
                # The resolver logic checks against loaded DF
                resolved = resolver.resolve(config)

                if resolved is None:
                    issues.append({
                        "source": "active_strategies.json",
                        "id": strat_id,
                        "error": f"Failed to resolve symbol for {config.get('symbol', 'unknown')}",
                        "status": "INVALID"
                    })
                elif isinstance(resolved, str):
                    # Check if resolved symbol exists in DF explicitly
                    if resolved not in resolver.df['symbol'].values:
                         issues.append({
                            "source": "active_strategies.json",
                            "id": strat_id,
                            "symbol": resolved,
                            "error": "Resolved symbol not found in master",
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

def scan_files_for_hardcoded_symbols(instruments):
    issues = []
    strategies_dir = os.path.join(REPO_ROOT, 'openalgo', 'strategies')

    if not os.path.exists(strategies_dir):
        return issues

    for root, dirs, files in os.walk(strategies_dir):
        # Exclude tests and pycache
        if 'tests' in dirs: dirs.remove('tests')
        if 'test' in dirs: dirs.remove('test')
        if '__pycache__' in dirs: dirs.remove('__pycache__')

        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
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
                            "source": os.path.basename(filepath),
                            "symbol": symbol_str,
                            "error": f"Invalid month: {parts[2]}",
                            "status": "INVALID"
                        })
                        continue

                    # Normalized form:
                    normalized = f"{parts[0].upper()}{int(parts[1]):02d}{parts[2].upper()}{parts[3]}FUT"

                    if symbol_str != normalized:
                         issues.append({
                            "source": os.path.basename(filepath),
                            "symbol": symbol_str,
                            "normalized": normalized,
                            "error": "Symbol is malformed (needs normalization)",
                            "status": "MALFORMED"
                        })

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
    print(f"Instrument Status: {msg}")

    if not fresh:
        if args.strict:
            print(f"❌ Strict Mode: Instrument check failed. {msg}")
            sys.exit(3) # Code 3 for missing/stale
        else:
            print("Warning: proceeding with stale/missing data.")

    # Load resolver
    resolver = None
    instruments = set()
    try:
        # Check if openalgo package is importable
        try:
            from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        except ImportError:
            sys.path.insert(0, os.path.join(REPO_ROOT, 'openalgo'))
            from strategies.utils.symbol_resolver import SymbolResolver

        resolver = SymbolResolver(INSTRUMENTS_FILE)
        if not resolver.df.empty:
            instruments = set(resolver.df['symbol'].unique())
        else:
            print("Warning: SymbolResolver loaded empty dataframe.")

    except Exception as e:
        print(f"Error loading SymbolResolver: {e}")
        # If strictly required, exit 3
        if args.strict and not fresh:
             sys.exit(3)
        # If fresh but failed to load, it's an error
        if args.strict:
             sys.exit(3)

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "strict_mode": args.strict,
        "instrument_status": msg,
        "issues": []
    }

    # 2. Validate Configs
    if resolver and not resolver.df.empty:
        print("Validating strategy configs...")
        config_issues = validate_config_symbols(resolver)
        audit_report["issues"].extend(config_issues)

    # 3. Validate Hardcoded Symbols
    if instruments:
        print("Scanning files for hardcoded symbols...")
        hardcoded_issues = scan_files_for_hardcoded_symbols(instruments)
        audit_report["issues"].extend(hardcoded_issues)
    else:
        print("Skipping file scan (no instruments loaded).")

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
    # In strict mode, any issue is a failure.
    # MALFORMED is also a failure in strict check mode (normalization required).

    invalid_issues = [i for i in audit_report["issues"] if i['status'] in ('INVALID', 'MISSING', 'ERROR')]
    malformed_issues = [i for i in audit_report["issues"] if i['status'] == 'MALFORMED']

    total_issues = len(invalid_issues) + len(malformed_issues)

    if total_issues > 0:
        print(f"❌ Validation Failed: {total_issues} issues found.")
        for issue in audit_report["issues"]:
            print(f" - [{issue['status']}] {issue.get('source')}: {issue.get('symbol', issue.get('id', 'Unknown'))} -> {issue.get('error')}")

        if args.strict:
             # If strict, any issue (including malformed) is exit 2
             sys.exit(2)
    else:
        print("✅ All symbols valid.")
        sys.exit(0)

if __name__ == "__main__":
    main()
