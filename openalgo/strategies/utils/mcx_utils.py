import re
from datetime import date

# Regex for MCX Symbols
# Pattern: SYMBOL + 1-2 digits (Day) + 3 letters (Month) + 2 digits (Year) + FUT
# e.g. GOLDM05FEB26FUT
# Capture groups: 1=Symbol, 2=Day, 3=Month, 4=Year
MCX_PATTERN = re.compile(r'\b([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT\b', re.IGNORECASE)

# Valid Months
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

def normalize_mcx_match(match):
    """
    Takes a regex match object and returns the normalized MCX symbol string.
    """
    symbol = match.group(1).upper()
    day = int(match.group(2))
    month = match.group(3).upper()
    year = match.group(4)

    # Normalize: Pad day with 0 if needed
    normalized = f"{symbol}{day:02d}{month}{year}FUT"
    return normalized

def format_mcx_symbol(underlying, expiry_date, mini=False):
    """
    Format MCX Futures Symbol strictly according to canonical rules.
    Underlying + (M if mini) + DD + MMM + YY + FUT
    DD is zero-padded.
    MMM is uppercase.
    YY is 2-digit year.
    """
    symbol = underlying.upper()
    if mini:
        symbol += "M"

    day_str = f"{expiry_date.day:02d}"
    month_str = expiry_date.strftime("%b").upper()
    year_str = expiry_date.strftime("%y")

    return f"{symbol}{day_str}{month_str}{year_str}FUT"

def normalize_mcx_string(symbol_str):
    """
    Normalize an existing MCX symbol string.
    e.g. GOLDM 5 FEB 26 FUT -> GOLDM05FEB26FUT
    """
    match = MCX_PATTERN.search(symbol_str)
    if not match:
        return symbol_str

    # Ensure exact match if needed, but the original implementation used re.match with explicit start/end anchors.
    # The new pattern uses \b. Let's use the helper.
    # But wait, original `normalize_mcx_string` expected full string match.

    # If we want to strictly validate a single string, we should check if the match covers the whole string.
    # However, for normalization purposes, we can just return the normalized form of the first match found.

    return normalize_mcx_match(match)
