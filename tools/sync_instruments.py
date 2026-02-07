#!/usr/bin/env python3
import os
import sys

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Add vendor directory to path to support 'from openalgo...' imports
vendor_dir = os.path.join(repo_root, 'vendor')
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

# Also add vendor/openalgo/scripts to path if needed for internal imports within daily_prep
scripts_dir = os.path.join(repo_root, 'vendor', 'openalgo', 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

try:
    from openalgo.scripts.daily_prep import fetch_instruments
except ImportError:
    # Fallback if package import fails, try direct import from scripts dir
    sys.path.insert(0, os.path.join(repo_root, 'vendor', 'openalgo'))
    try:
        from scripts.daily_prep import fetch_instruments
    except ImportError:
        # Last resort: direct file import
        import importlib.util
        spec = importlib.util.spec_from_file_location("daily_prep", os.path.join(scripts_dir, "daily_prep.py"))
        daily_prep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(daily_prep)
        fetch_instruments = daily_prep.fetch_instruments

def main():
    print("🔄 Syncing instruments...")
    try:
        fetch_instruments()
        print("✅ Instruments synced.")
    except Exception as e:
        print(f"❌ Failed to sync instruments: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
