# OpenAlgo Daily Preparation & Validation

This guide outlines the daily workflow for OpenAlgo, ensuring a clean state, valid symbols, and system readiness before trading.

## 1. Daily Startup Routine

The single entry point for daily operations is `daily_startup.py`. This script orchestrates the entire preparation process.

### Usage
```bash
# Standard Daily Prep (Run before market open)
python3 daily_startup.py

# Run with Backtesting & Leaderboard (Optional)
python3 daily_startup.py --backtest
```

### What It Does
1.  **Repo Verification**: Ensures `openalgo` codebase is present and correct.
2.  **Environment Check**: Validates API keys and paths.
3.  **State Purge**:
    *   Deletes `openalgo/sessions/` (forces fresh login).
    *   Deletes `openalgo/data/instruments.csv` (forces fresh instrument fetch).
4.  **Authentication**: Runs health check (`authentication_health_check.py`).
5.  **Instrument Refresh**: Fetches latest instruments from API (or generates dynamic mocks if API unavailable).
6.  **Symbol Validation**:
    *   Loads `active_strategies.json`.
    *   Resolves all configured symbols to tradable instrument IDs.
    *   **Fails Fast** if any symbol is invalid.
7.  **Success Marker**: Creates `.daily_prep_passed` file. Strategies will **refuse to trade** if this file is missing or stale (from previous day).

---

## 2. Symbol Formatting Rules

Strategies should use `SymbolResolver` to automatically handle formatting. However, manual configurations in `active_strategies.json` follow these rules:

### NSE Equity
*   **Format**: `SYMBOL` (e.g., `RELIANCE`, `INFY`)
*   **Resolver Logic**: Checks `instruments.csv` for EQ segment match.

### NSE Futures
*   **Format**: `SYMBOL` + `Expiry` (e.g., `NIFTY26FEBFUT`)
*   **Resolver Logic**: Provide `underlying: "NIFTY", type: "FUT"`. The resolver automatically picks the **current month** or **nearest** expiry.

### NSE Options
*   **Configuration**:
    ```json
    {
        "underlying": "NIFTY",
        "type": "OPT",
        "option_type": "CE",
        "expiry_preference": "WEEKLY", // or "MONTHLY"
        "strike_criteria": "ATM" // or "ITM", "OTM"
    }
    ```
*   **Resolver Logic**:
    *   **WEEKLY**: Selects the nearest weekly expiry.
    *   **MONTHLY**: Selects the last expiry of the current month cycle.
    *   **Strike**: Automatically calculates based on Spot Price (if available) or returns sample symbol.

### MCX Futures (Commodities)
*   **Requirement**: **Prefer MINI contracts**.
*   **Resolver Logic**:
    *   Input: `underlying: "SILVER", type: "FUT"`
    *   Action: Searches for symbols containing `MINI` or following the `{UNDERLYING}M...` pattern (e.g., `SILVERMIC...`, `GOLDM...`).
    *   **Fallback**: If no MINI contract is found, defaults to standard contract (`SILVER...`).

---

## 3. Troubleshooting Playbook

### Issue: "Daily Prep NOT Passed. Trading Aborted."
*   **Cause**: You tried to run a strategy directly without running `daily_startup.py` first, or the prep failed.
*   **Fix**: Run `python3 daily_startup.py` and check for green success messages.

### Issue: "Authentication check failed!"
*   **Cause**: API Key invalid, Broker API down, or TOTP expired.
*   **Fix**:
    1.  Check `OPENALGO_APIKEY` environment variable.
    2.  Check `openalgo/logs/` for specific auth errors.
    3.  Manually run `python3 openalgo/scripts/authentication_health_check.py` to diagnose.

### Issue: "Found X invalid symbols!"
*   **Cause**: Strategy config in `active_strategies.json` references an expired contract or invalid underlying.
*   **Fix**:
    1.  Check the `SYMBOL VALIDATION REPORT` output.
    2.  Update `active_strategies.json` with correct underlying names (e.g., ensure `NIFTY 50` vs `NIFTY`).
    3.  Verify `instruments.csv` was fetched correctly.

### Issue: "Backtest failed: No data available"
*   **Cause**: API connection refused or no historical data access.
*   **Fix**: Ensure `OPENALGO_HOST` is pointing to a running OpenAlgo server with valid data subscription.
