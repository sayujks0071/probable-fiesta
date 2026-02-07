import re
from datetime import date

# Regex for MCX Symbols (Loose/Fuzzy)
# Allows optional spaces between parts
# Captures: 1=Symbol, 2=Day, 3=Month, 4=Year
# Example matches: GOLDM05FEB26FUT, GOLDM 5 FEB 26 FUT, SILVERMIC 28 FEB 25 FUT
MCX_FUZZY_PATTERN = re.compile(r'\b([A-Z]+)\s*(\d{1,2})\s*([A-Z]{3})\s*(\d{2})\s*FUT\b', re.IGNORECASE)

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
    Returns the normalized symbol if it matches the MCX pattern, otherwise returns original.
    """
    if not symbol_str:
        return symbol_str

    clean_str = symbol_str.strip()
    match = MCX_FUZZY_PATTERN.match(clean_str) # match checks from beginning
    if not match:
        # Try search if match failed (though pattern has \b)
        match = MCX_FUZZY_PATTERN.search(clean_str)
        if not match:
             return symbol_str

    sym = match.group(1).upper()
    day = int(match.group(2))
    month = match.group(3).upper()
    year = match.group(4)

    return f"{sym}{day:02d}{month}{year}FUT"

def normalize_mcx_fuzzy(text):
    """
    Scans a text block and normalizes all occurrences of MCX symbols.
    Useful for fixing files or logs.
    """
    def repl(m):
        sym = m.group(1).upper()
        day = int(m.group(2))
        month = m.group(3).upper()
        year = m.group(4)
        return f"{sym}{day:02d}{month}{year}FUT"

    return MCX_FUZZY_PATTERN.sub(repl, text)
