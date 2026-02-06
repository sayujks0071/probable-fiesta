import pytest
import sys
import os
from datetime import date

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

def test_format_mcx_symbol_strict():
    # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
    assert format_mcx_symbol('GOLD', date(2026, 2, 5), mini=True) == 'GOLDM05FEB26FUT'

    # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
    assert format_mcx_symbol('SILVER', date(2026, 2, 27), mini=True) == 'SILVERM27FEB26FUT'

    # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
    assert format_mcx_symbol('CRUDEOIL', date(2026, 2, 19), mini=False) == 'CRUDEOIL19FEB26FUT'

def test_format_mcx_symbol_padding():
    # Day padding: 5 -> 05
    assert format_mcx_symbol('TEST', date(2026, 1, 5), mini=False) == 'TEST05JAN26FUT'
    # Day padding: 15 -> 15
    assert format_mcx_symbol('TEST', date(2026, 1, 15), mini=False) == 'TEST15JAN26FUT'

def test_format_mcx_symbol_uppercase():
    # Month uppercase: may -> MAY
    # Note: strftime usually handles case, but we ensure output is upper
    # Python's %b is locale dependent but typically Title case in EN.
    # The util explicitly calls .upper()
    assert format_mcx_symbol('TEST', date(2026, 5, 10), mini=False) == 'TEST10MAY26FUT'

def test_format_mcx_symbol_year():
    # Year: 2026 -> 26
    assert format_mcx_symbol('TEST', date(2026, 12, 31), mini=False) == 'TEST31DEC26FUT'

def test_normalize_mcx_string():
    # Normalization check
    # Check handling of spaces
    assert normalize_mcx_string('GOLDM 5 FEB 26 FUT') == 'GOLDM05FEB26FUT'
    # Check handling of missing padding
    assert normalize_mcx_string('GOLDM5FEB26FUT') == 'GOLDM05FEB26FUT'
    # Check already normalized
    assert normalize_mcx_string('GOLDM05FEB26FUT') == 'GOLDM05FEB26FUT'
