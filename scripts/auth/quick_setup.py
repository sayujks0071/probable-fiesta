#!/usr/bin/env python3
"""
Quick Setup Script for Trading Platform Authentication
Run this script to initialize credentials and authenticate.

Usage:
    python quick_setup.py
"""
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from credentials import CredentialManager


def main():
    print("=" * 60)
    print("Trading Platform Authentication Setup")
    print("=" * 60)

    # Initialize credential manager
    manager = CredentialManager()

    # Store OpenAlgo credentials
    print("\n[1/2] Storing OpenAlgo credentials...")
    manager.set_credential(
        platform="openalgo",
        username="sayujks0071",
        password="Apollo@20417",
        email="sayujks0071@openalgo.local"
    )
    print("      Username: sayujks0071")
    print("      Status: Stored securely")

    # Store Kite credentials
    print("\n[2/2] Storing Kite (Zerodha) credentials...")
    manager.set_credential(
        platform="kite",
        username="MM2076",
        password="Apollo@20417",
        broker="zerodha"
    )
    print("      Username: MM2076")
    print("      Status: Stored securely")

    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)

    print("\nStored platforms:", manager.list_platforms())

    print("\nNext steps:")
    print("  1. For OpenAlgo: Start the server and login at http://127.0.0.1:5000")
    print("  2. For Kite: Configure BROKER_API_KEY and BROKER_API_SECRET in .env")
    print("     Then run: python auto_login.py --login kite")

    print("\nTo run automated login:")
    print("  python auto_login.py --setup")

    return 0


if __name__ == "__main__":
    sys.exit(main())
