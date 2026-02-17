#!/usr/bin/env python3
import os
import sys

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Also add openalgo/scripts to path if needed for internal imports within daily_prep
scripts_dir = os.path.join(repo_root, 'openalgo', 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

try:
    from openalgo.scripts.daily_prep import fetch_instruments, check_login
except ImportError:
    # Fallback if openalgo package is not directly importable (e.g. not installed)
    sys.path.insert(0, os.path.join(repo_root, 'openalgo'))
    from scripts.daily_prep import fetch_instruments, check_login

def main():
    print("🔄 Syncing instruments...")
    try:
        # Ensure environment is set up for login (e.g. API keys)
        # If check_login relies on env vars, they must be present.
        # If check_login fails, it might exit or return None.

        # We can suppress logging from daily_prep if we want, but CI logs are useful.
        client = check_login()

        if client:
            fetch_instruments(client)
            print("✅ Instruments synced.")
        else:
            print("❌ Failed to initialize API Client.")
            sys.exit(1)

    except SystemExit as e:
        # check_login or fetch_instruments might sys.exit
        sys.exit(e.code)
    except Exception as e:
        print(f"❌ Failed to sync instruments: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
