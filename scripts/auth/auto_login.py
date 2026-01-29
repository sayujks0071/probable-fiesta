#!/usr/bin/env python3
"""
Automated Login Utility for Trading Platforms
Handles OpenAlgo user setup and Kite/Zerodha OAuth authentication.
Designed for fast, automated login flows.
"""
import os
import sys
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "openalgo"))
sys.path.insert(0, str(PROJECT_ROOT / "AITRAPP" / "AITRAPP"))

import requests
from dotenv import load_dotenv, set_key

# Load environment
load_dotenv(PROJECT_ROOT / "openalgo" / ".env")
load_dotenv(PROJECT_ROOT / "AITRAPP" / "AITRAPP" / ".env")

from credentials import CredentialManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OpenAlgoAuth:
    """Handle OpenAlgo user authentication."""

    def __init__(self, base_url: str = "http://127.0.0.1:5000"):
        self.base_url = base_url
        self.session = requests.Session()

    def register_user(self, username: str, email: str, password: str) -> bool:
        """
        Register a new user in OpenAlgo database.

        Uses direct database access since registration endpoint may not exist.
        """
        try:
            from database.user_db import add_user, init_db

            # Initialize database
            init_db()

            # Add user
            user = add_user(username, email, password, is_admin=True)
            if user:
                logger.info(f"User '{username}' registered successfully")
                return True
            else:
                logger.warning(f"User '{username}' may already exist")
                return False
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    def login(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Login to OpenAlgo application.

        Returns:
            Tuple of (success, session_cookie)
        """
        try:
            # Get CSRF token first
            resp = self.session.get(f"{self.base_url}/auth/login")
            if resp.status_code != 200:
                return False, None

            # Attempt login
            login_data = {
                "username": username,
                "password": password
            }
            resp = self.session.post(
                f"{self.base_url}/auth/login",
                data=login_data,
                allow_redirects=False
            )

            if resp.status_code in [200, 302]:
                logger.info(f"OpenAlgo login successful for '{username}'")
                return True, self.session.cookies.get('session')
            else:
                logger.error(f"Login failed with status {resp.status_code}")
                return False, None

        except requests.exceptions.ConnectionError:
            logger.warning("OpenAlgo server not running. Use direct DB auth.")
            return self._direct_auth(username, password)
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, None

    def _direct_auth(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Authenticate directly against database."""
        try:
            from database.user_db import authenticate_user
            if authenticate_user(username, password):
                logger.info(f"Direct authentication successful for '{username}'")
                return True, "direct_auth_session"
            return False, None
        except Exception as e:
            logger.error(f"Direct auth failed: {e}")
            return False, None


class KiteAuth:
    """Handle Kite/Zerodha OAuth authentication."""

    LOGIN_URL = "https://kite.zerodha.com/connect/login"
    TWOFA_URL = "https://kite.zerodha.com/connect/twofa"
    API_SESSION_URL = "https://api.kite.trade/session/token"

    def __init__(self):
        self.api_key = os.getenv("BROKER_API_KEY") or os.getenv("KITE_API_KEY")
        self.api_secret = os.getenv("BROKER_API_SECRET") or os.getenv("KITE_API_SECRET")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def get_login_url(self) -> str:
        """Get Kite Connect login URL."""
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={self.api_key}"

    def automated_login(
        self,
        username: str,
        password: str,
        totp_secret: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Perform automated Kite login.

        Note: This requires the Kite app to be configured for API access.
        The login flow returns a request_token which is exchanged for access_token.

        Args:
            username: Kite user ID
            password: Kite password
            totp_secret: TOTP secret for 2FA (optional, manual if not provided)

        Returns:
            Tuple of (success, access_token)
        """
        try:
            # Step 1: Initial login
            login_url = self.get_login_url()
            logger.info(f"Starting Kite login for user: {username}")

            resp = self.session.get(login_url)
            if resp.status_code != 200:
                logger.error("Failed to load Kite login page")
                return False, None

            # Step 2: Submit credentials
            login_data = {
                "user_id": username,
                "password": password
            }
            resp = self.session.post(self.LOGIN_URL, data=login_data)

            if "Invalid" in resp.text or resp.status_code != 200:
                logger.error("Invalid Kite credentials")
                return False, None

            # Step 3: Handle 2FA if required
            if "twofa" in resp.url or "Enter your PIN" in resp.text:
                if totp_secret:
                    import pyotp
                    totp = pyotp.TOTP(totp_secret)
                    twofa_pin = totp.now()
                else:
                    logger.info("2FA required. Enter PIN manually or provide TOTP secret.")
                    twofa_pin = input("Enter Kite PIN/TOTP: ")

                twofa_data = {
                    "user_id": username,
                    "twofa_value": twofa_pin
                }
                resp = self.session.post(self.TWOFA_URL, data=twofa_data)

            # Step 4: Extract request_token from redirect
            if "request_token" in resp.url:
                parsed = urlparse(resp.url)
                params = parse_qs(parsed.query)
                request_token = params.get("request_token", [None])[0]

                if request_token:
                    return self.exchange_token(request_token)

            # Check for request_token in response
            if resp.history:
                for r in resp.history:
                    if "request_token" in r.url:
                        parsed = urlparse(r.url)
                        params = parse_qs(parsed.query)
                        request_token = params.get("request_token", [None])[0]
                        if request_token:
                            return self.exchange_token(request_token)

            logger.warning("Could not extract request_token from Kite login flow")
            logger.info(f"Login URL for manual authentication: {login_url}")
            return False, None

        except Exception as e:
            logger.error(f"Kite login error: {e}")
            return False, None

    def exchange_token(self, request_token: str) -> Tuple[bool, Optional[str]]:
        """
        Exchange request_token for access_token.

        Args:
            request_token: Token received from Kite OAuth callback

        Returns:
            Tuple of (success, access_token)
        """
        try:
            # Generate checksum
            checksum_str = f"{self.api_key}{request_token}{self.api_secret}"
            checksum = hashlib.sha256(checksum_str.encode()).hexdigest()

            data = {
                "api_key": self.api_key,
                "request_token": request_token,
                "checksum": checksum
            }

            headers = {"X-Kite-Version": "3"}
            resp = requests.post(self.API_SESSION_URL, data=data, headers=headers)

            if resp.status_code == 200:
                result = resp.json()
                if "data" in result and "access_token" in result["data"]:
                    access_token = result["data"]["access_token"]
                    user_id = result["data"].get("user_id", "")

                    # Persist token
                    self._persist_token(access_token, user_id)

                    logger.info(f"Kite access token obtained for user: {user_id}")
                    return True, access_token

            logger.error(f"Token exchange failed: {resp.text}")
            return False, None

        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return False, None

    def _persist_token(self, access_token: str, user_id: str):
        """Save access token to environment files."""
        # Update OpenAlgo .env
        openalgo_env = PROJECT_ROOT / "openalgo" / ".env"
        if openalgo_env.exists():
            # Note: For OpenAlgo, the token is stored in database, not .env

            pass

        # Update AITRAPP .env
        aitrapp_env = PROJECT_ROOT / "AITRAPP" / "AITRAPP" / ".env"
        if aitrapp_env.exists():
            set_key(str(aitrapp_env), "KITE_ACCESS_TOKEN", access_token)
            set_key(str(aitrapp_env), "KITE_USER_ID", user_id)
            logger.info("Access token saved to AITRAPP/.env")

        # Also set in current environment
        os.environ["KITE_ACCESS_TOKEN"] = access_token
        os.environ["KITE_USER_ID"] = user_id

    def validate_session(self) -> bool:
        """Check if current access token is valid."""
        access_token = os.getenv("KITE_ACCESS_TOKEN")
        if not access_token:
            return False

        try:
            headers = {
                "X-Kite-Version": "3",
                "Authorization": f"token {self.api_key}:{access_token}"
            }
            resp = requests.get(
                "https://api.kite.trade/user/profile",
                headers=headers
            )
            return resp.status_code == 200
        except Exception:
            return False


class AutoLogin:
    """Main automated login orchestrator."""

    def __init__(self):
        self.cred_manager = CredentialManager()
        self.openalgo = OpenAlgoAuth()
        self.kite = KiteAuth()

    def setup_all(self) -> dict:
        """
        Set up authentication for all configured platforms.

        Returns:
            Dict with status for each platform
        """
        results = {}

        # Setup OpenAlgo
        openalgo_creds = self.cred_manager.get_credential("openalgo")
        if openalgo_creds:
            logger.info("Setting up OpenAlgo authentication...")
            self.openalgo.register_user(
                openalgo_creds["username"],
                openalgo_creds.get("email", f"{openalgo_creds['username']}@local"),
                openalgo_creds["password"]
            )
            success, _ = self.openalgo.login(
                openalgo_creds["username"],
                openalgo_creds["password"]
            )
            results["openalgo"] = "success" if success else "failed"

        # Setup Kite
        kite_creds = self.cred_manager.get_credential("kite")
        if kite_creds:
            logger.info("Setting up Kite authentication...")

            # First check if we have a valid session
            if self.kite.validate_session():
                logger.info("Existing Kite session is valid")
                results["kite"] = "existing_valid"
            else:
                success, token = self.kite.automated_login(
                    kite_creds["username"],
                    kite_creds["password"],
                    kite_creds.get("totp_secret")
                )
                results["kite"] = "success" if success else "manual_required"

                if not success:
                    logger.info(
                        f"Manual Kite login required. URL: {self.kite.get_login_url()}"
                    )

        return results

    def quick_login(self, platform: str) -> bool:
        """
        Quick login to a specific platform.

        Args:
            platform: 'openalgo' or 'kite'

        Returns:
            Success status
        """
        creds = self.cred_manager.get_credential(platform)
        if not creds:
            logger.error(f"No credentials found for {platform}")
            return False

        if platform == "openalgo":
            success, _ = self.openalgo.login(
                creds["username"],
                creds["password"]
            )
            return success

        elif platform == "kite":
            if self.kite.validate_session():
                return True
            success, _ = self.kite.automated_login(
                creds["username"],
                creds["password"],
                creds.get("totp_secret")
            )
            return success

        return False


def main():
    """Main entry point for automated login."""
    import argparse

    parser = argparse.ArgumentParser(description="Automated Trading Platform Login")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Initial setup - store credentials and authenticate"
    )
    parser.add_argument(
        "--login",
        choices=["openalgo", "kite", "all"],
        help="Login to specific platform"
    )
    parser.add_argument(
        "--store-creds",
        action="store_true",
        help="Store default credentials"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate existing sessions"
    )

    args = parser.parse_args()

    auto_login = AutoLogin()

    if args.store_creds or args.setup:
        from credentials import setup_default_credentials
        setup_default_credentials()

    if args.setup:
        results = auto_login.setup_all()
        print("\nSetup Results:")
        for platform, status in results.items():
            print(f"  {platform}: {status}")

    elif args.login:
        if args.login == "all":
            results = auto_login.setup_all()
            for platform, status in results.items():
                print(f"{platform}: {status}")
        else:
            success = auto_login.quick_login(args.login)
            print(f"{args.login}: {'success' if success else 'failed'}")

    elif args.validate:
        kite = KiteAuth()
        print(f"Kite session valid: {kite.validate_session()}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
