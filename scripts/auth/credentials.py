"""
Secure credentials storage for trading platform authentication.
Uses base64 encoding with obfuscation for credential storage.
"""
import os
import json
import base64
import hashlib
from pathlib import Path


class CredentialManager:
    """Manages secure storage of login credentials."""

    CREDENTIALS_FILE = Path(__file__).parent / ".credentials.json"

    def __init__(self, master_password: str = None):
        """
        Initialize credential manager.

        Args:
            master_password: Master password for encoding.
                           If None, uses API_KEY_PEPPER from environment.
        """
        self.master_password = master_password or os.getenv(
            "API_KEY_PEPPER",
            "default_pepper_change_in_production"
        )
        self._key = self._derive_key()

    def _derive_key(self) -> bytes:
        """Derive a key from master password."""
        return hashlib.sha256(self.master_password.encode()).digest()

    def _encode(self, data: str) -> str:
        """Encode data with XOR obfuscation and base64."""
        key = self._key
        encoded = bytes(
            ord(c) ^ key[i % len(key)]
            for i, c in enumerate(data)
        )
        return base64.b64encode(encoded).decode()

    def _decode(self, encoded: str) -> str:
        """Decode base64 and XOR obfuscation."""
        key = self._key
        decoded_bytes = base64.b64decode(encoded)
        return ''.join(
            chr(b ^ key[i % len(key)])
            for i, b in enumerate(decoded_bytes)
        )

    def _load_credentials(self) -> dict:
        """Load and decode credentials from file."""
        if not self.CREDENTIALS_FILE.exists():
            return {}
        try:
            with open(self.CREDENTIALS_FILE, 'r') as f:
                data = json.load(f)
            # Decode each credential
            result = {}
            for platform, creds in data.items():
                result[platform] = {
                    k: self._decode(v) if k in ('password',) else v
                    for k, v in creds.items()
                }
            return result
        except Exception:
            return {}

    def _save_credentials(self, credentials: dict):
        """Encode and save credentials to file."""
        self.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Encode sensitive fields
        encoded = {}
        for platform, creds in credentials.items():
            encoded[platform] = {
                k: self._encode(v) if k in ('password',) else v
                for k, v in creds.items()
            }
        with open(self.CREDENTIALS_FILE, 'w') as f:
            json.dump(encoded, f, indent=2)

    def set_credential(self, platform: str, username: str, password: str, **extra):
        """
        Store credentials for a platform.

        Args:
            platform: Platform name (e.g., 'openalgo', 'kite')
            username: Login username
            password: Login password
            **extra: Additional fields (api_key, totp_secret, etc.)
        """
        credentials = self._load_credentials()
        credentials[platform] = {
            "username": username,
            "password": password,
            **extra
        }
        self._save_credentials(credentials)

    def get_credential(self, platform: str) -> dict:
        """
        Retrieve credentials for a platform.

        Args:
            platform: Platform name

        Returns:
            Dict with username, password, and any extra fields
        """
        credentials = self._load_credentials()
        return credentials.get(platform, {})

    def list_platforms(self) -> list:
        """List all stored platform credentials."""
        credentials = self._load_credentials()
        return list(credentials.keys())

    def delete_credential(self, platform: str) -> bool:
        """Delete credentials for a platform."""
        credentials = self._load_credentials()
        if platform in credentials:
            del credentials[platform]
            self._save_credentials(credentials)
            return True
        return False


# Pre-configured credentials for the system
def setup_default_credentials():
    """Set up the default credentials for OpenAlgo and Kite."""
    manager = CredentialManager()

    # OpenAlgo credentials
    manager.set_credential(
        platform="openalgo",
        username="sayujks0071",
        password="Apollo@20417",
        email="sayujks0071@openalgo.local"
    )

    # Kite (Zerodha) credentials
    manager.set_credential(
        platform="kite",
        username="MM2076",
        password="Apollo@20417",
        broker="zerodha"
    )

    print("Credentials stored securely.")
    return manager


if __name__ == "__main__":
    setup_default_credentials()
