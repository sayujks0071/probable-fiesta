# Symbol Resolution Guide

OpenAlgo employs a sophisticated `SymbolResolver` to translate human-readable strategy inputs into broker-valid instrument symbols.

## Supported Instrument Types

### 1. NSE Equity (Cash/Futures)

*   **Config:** `type: "EQUITY"`, `symbol: "RELIANCE"`
*   **Resolver Logic:** Looks for `instrument_type="EQ"` and matching name.
*   **Validation:** Fails if symbol not found in `instruments.csv`.

### 2. NSE Futures

*   **Config:** `type: "FUT"`, `underlying: "NIFTY"`, `exchange: "NFO"`
*   **Resolver Logic:**
    *   Finds instruments with `instrument_type="FUT"` and matching name.
    *   Selects the **Nearest Expiry** future (e.g., `NIFTY23OCTFUT`).
*   **Validation:** Fails if no future contract is found for the underlying.

### 3. NSE Options

*   **Config:**
    *   `type: "OPT"`
    *   `underlying: "NIFTY"` (or `NIFTY 50`, `NIFTY BANK`)
    *   `option_type: "CE"` or `"PE"`
    *   `expiry_preference: "WEEKLY"` or `"MONTHLY"`
    *   `strike_criteria: "ATM"`, `"ITM"`, `"OTM"`

*   **Resolver Logic:**
    *   **Expiry Selection:**
        *   `WEEKLY`: Selects the *next available* expiry date (e.g., nearest Thursday).
        *   `MONTHLY`: Selects the *last expiry of the current month*.
    *   **Strike Selection:**
        *   `ATM`: Selects the strike closest to the current Spot Price.
        *   `ITM`: Selects 1 strike deeper In-The-Money (Lower for Call, Higher for Put).
        *   `OTM`: Selects 1 strike deeper Out-Of-The-Money (Higher for Call, Lower for Put).

### 4. MCX Commodity Futures

*   **Config:** `type: "FUT"`, `underlying: "SILVER"`, `exchange: "MCX"`
*   **Resolver Logic:**
    *   **MINI Preference:** Automatically checks for MINI contracts first.
        *   Matches regex `^{NAME}M\d` (e.g., `SILVERM...`) or `MINI` in symbol.
        *   Example: Resolves `SILVER` -> `SILVERM23NOVFUT` (if available).
    *   **Fallback:** If no MINI contract is found, falls back to the standard contract (e.g., `SILVER23NOVFUT`).

## Configuration Example (active_strategies.json)

```json
{
    "SuperTrend_NIFTY": {
        "symbol": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE"
    },
    "MCX_SILVER": {
        "underlying": "SILVER",
        "type": "FUT",
        "exchange": "MCX"
    },
    "NIFTY_OPT_STRATEGY": {
        "underlying": "NIFTY",
        "type": "OPT",
        "option_type": "CE",
        "expiry_preference": "WEEKLY",
        "strike_criteria": "ATM",
        "exchange": "NFO"
    }
}
```

## Adding New Symbols

Ensure the instrument exists in `openalgo/data/instruments.csv`.
If running offline, `daily_prep.py` generates a Mock list covering:
*   `NIFTY`, `RELIANCE`, `INFY` (Equity)
*   `SILVER`, `GOLD` (MCX Futures, including MINI/MICRO variants)
*   `NIFTY` (NSE Futures & Options)
