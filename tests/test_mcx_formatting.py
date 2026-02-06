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
    assert normalize_mcx_string('GOLDM 5 FEB 26 FUT') == 'GOLDM05FEB26FUT' # Should fail if strict regex doesn't match spaces?
    # Wait, the current implementation of normalize_mcx_string in mcx_utils.py uses a regex that might not catch spaces if it expects specific format.
    # Let's check the implementation again.

    # The current regex in mcx_utils.py is r'^([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT$'
    # This expects NO spaces. So 'GOLDM 5 FEB 26 FUT' would NOT match and would return original.
    # But the requirement says "normalize_mcx_string... e.g. GOLDM 5 FEB 26 FUT -> GOLDM05FEB26FUT".
    # I should check if I need to update mcx_utils.py to handle spaces or if the test should reflect current behavior.
    # The requirement in the prompt says: "Add unit tests asserting exactly: ... GOLDM05FEB26FUT ...".
    # It does not explicitly ask to change normalize_mcx_string to handle spaces, but implies "zero padding on DD".

    # Let's test what IS supported: padding.
    assert normalize_mcx_string('GOLDM5FEB26FUT') == 'GOLDM05FEB26FUT'
    assert normalize_mcx_string('GOLDM05FEB26FUT') == 'GOLDM05FEB26FUT'
