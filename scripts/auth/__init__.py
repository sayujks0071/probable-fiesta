"""
Authentication utilities for trading platforms.
Provides secure credential storage and automated login flows.
"""
from .credentials import CredentialManager, setup_default_credentials
from .auto_login import AutoLogin, OpenAlgoAuth, KiteAuth

__all__ = [
    "CredentialManager",
    "setup_default_credentials",
    "AutoLogin",
    "OpenAlgoAuth",
    "KiteAuth",
]
