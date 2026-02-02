import sys
import os
import re
import pytest
from datetime import date

# Add tools to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from tools.normalize_symbols_repo import normalize_mcx_symbol, MCX_PATTERN

def test_mcx_strict_formatting():
    """
    Test strict MCX formatting requirements:
    - GOLDM05FEB26FUT for date(2026,2,5) with mini=True
    - SILVERM27FEB26FUT for date(2026,2,27) with mini=True
    - CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
    """

    test_cases = [
        # (Input Symbol, Expected Normalized)
        ("GOLDM5FEB26FUT", "GOLDM05FEB26FUT"),       # Test zero padding
        ("GOLDM05FEB26FUT", "GOLDM05FEB26FUT"),      # Already correct
        ("SILVERM27FEB26FUT", "SILVERM27FEB26FUT"),  # Correct
        ("CRUDEOIL19FEB26FUT", "CRUDEOIL19FEB26FUT"),# Correct
        ("goldm5feb26fut", "GOLDM05FEB26FUT"),       # Lowercase input
        ("CrudeOil19Feb26Fut", "CRUDEOIL19FEB26FUT") # Mixed case
    ]

    for input_sym, expected in test_cases:
        match = MCX_PATTERN.search(input_sym)
        assert match is not None, f"Failed to match {input_sym}"
        normalized = normalize_mcx_symbol(match)
        assert normalized == expected, f"Failed for {input_sym}: Got {normalized}, Expected {expected}"

def test_mcx_components():
    """Test specific components logic if needed"""
    # Verify regex groups
    # Pattern: SYMBOL + Day + Month + Year + FUT
    # GOLDM 05 FEB 26 FUT

    sym = "GOLDM05FEB26FUT"
    match = MCX_PATTERN.search(sym)
    assert match.group(1) == "GOLDM"
    assert match.group(2) == "05"
    assert match.group(3) == "FEB"
    assert match.group(4) == "26"

    sym = "SILVERM27FEB26FUT"
    match = MCX_PATTERN.search(sym)
    assert match.group(1) == "SILVERM"
    assert match.group(2) == "27"
    assert match.group(3) == "FEB"
    assert match.group(4) == "26"

def test_mcx_single_digit_day():
    sym = "GOLDM5FEB26FUT"
    match = MCX_PATTERN.search(sym)
    assert match.group(2) == "5"
    normalized = normalize_mcx_symbol(match)
    assert normalized == "GOLDM05FEB26FUT"
