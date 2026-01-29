#!/usr/bin/env python3
"""
Kite Token Exchange Script
Run this locally to exchange request_token for access_token.

Usage:
    python kite_token_exchange.py <request_token>

Example:
    python kite_token_exchange.py xCNHuQ1ZLkb7u6WvzHwYyBVWJEfE94JR
"""
import sys
import hashlib

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# Your Kite API credentials
API_KEY = "nhe2vo0afks02ojs"
API_SECRET = "7suy2gunydkuzaejogbnqme7ksc3wwxc"

def exchange_token(request_token: str) -> dict:
    """Exchange request_token for access_token."""
    url = "https://api.kite.trade/session/token"

    # Generate checksum
    checksum_str = f"{API_KEY}{request_token}{API_SECRET}"
    checksum = hashlib.sha256(checksum_str.encode()).hexdigest()

    data = {
        "api_key": API_KEY,
        "request_token": request_token,
        "checksum": checksum
    }

    headers = {"X-Kite-Version": "3"}

    response = requests.post(url, data=data, headers=headers)
    return response.json()

def main():
    if len(sys.argv) < 2:
        # Use default request_token if not provided
        request_token = "xCNHuQ1ZLkb7u6WvzHwYyBVWJEfE94JR"
        print(f"Using default request_token: {request_token}")
    else:
        request_token = sys.argv[1]

    print(f"\nExchanging request_token: {request_token}")
    print("-" * 50)

    try:
        result = exchange_token(request_token)

        if "data" in result and "access_token" in result["data"]:
            access_token = result["data"]["access_token"]
            user_id = result["data"].get("user_id", "")

            print(f"\n✓ SUCCESS!")
            print(f"\nUser ID: {user_id}")
            print(f"Access Token: {access_token}")

            # Generate the combined token format for OpenAlgo
            combined_token = f"{API_KEY}:{access_token}"
            print(f"\nOpenAlgo Auth Token: {combined_token}")

            # Save to file
            with open("kite_token.txt", "w") as f:
                f.write(f"USER_ID={user_id}\n")
                f.write(f"ACCESS_TOKEN={access_token}\n")
                f.write(f"OPENALGO_AUTH_TOKEN={combined_token}\n")
            print("\nSaved to kite_token.txt")

        else:
            print(f"\n✗ FAILED")
            print(f"Response: {result}")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")

if __name__ == "__main__":
    main()
