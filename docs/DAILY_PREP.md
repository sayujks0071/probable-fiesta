# Daily Trading Preparation Guide

This document outlines the daily startup routine for OpenAlgo. This routine ensures a clean environment, valid symbols, and updated instruments before any trading activity begins.

## Command

The daily startup is managed by a single entrypoint script:

```bash
python3 daily_startup.py
```

### Options

*   `--backtest`: Runs the daily backtest and leaderboard generation after preparation.

```bash
python3 daily_startup.py --backtest
```

## Workflow Steps

The `daily_startup.py` script orchestrates the following:

1.  **Repository Check:**
    *   Ensures `vendor/openalgo` exists.
    *   Clones the repository if missing.

2.  **Daily Prep (`vendor/openalgo/scripts/daily_prep.py`):**
    *   **Environment Check:** Verifies API keys and directory structure.
    *   **Purge Stale State:**
        *   Deletes state files (`*.json`) from `vendor/openalgo/strategies/state/`.
        *   Deletes cached `instruments.csv`.
        *   Purges `vendor/openalgo/sessions/` directory.
    *   **Authentication:**
        *   Runs a health check on authentication.
        *   If the health check script is missing, it mocks a successful login session for testing.
    *   **Fetch Instruments:**
        *   Downloads the latest `instruments.csv` from the API.
        *   If the API is unreachable, generates a comprehensive Mock Instrument list (including NSE Options and MCX Futures).
    *   **Symbol Validation:**
        *   Reads `vendor/openalgo/strategies/active_strategies.json`.
        *   Resolves each configured symbol using `SymbolResolver`.
        *   **Halts Execution** if any invalid symbols are found.

3.  **Backtest Leaderboard (`vendor/openalgo/scripts/daily_backtest_leaderboard.py`)** (Optional):
    *   Loads configured strategies.
    *   Runs a base backtest on the last 5 days.
    *   Selects top 3 strategies.
    *   Runs an optimization loop (variants of key parameters).
    *   Generates `LEADERBOARD.md` and `leaderboard.json`.

## Troubleshooting

### "Invalid Symbol" Error
*   Check `active_strategies.json`.
*   Ensure the `underlying` matches an instrument in `instruments.csv`.
*   For Options, ensure `expiry_preference` ('WEEKLY'/'MONTHLY') is valid for the current date.

### "API Connection Failed"
*   Ensure the OpenAlgo API server is running on localhost:5001.
*   If running in offline mode, the script will automatically fallback to Mock Instruments.

### "ImportError: No module named openalgo"
*   Ensure `vendor/` is in your `PYTHONPATH`.
*   `daily_startup.py` automatically sets this up. Always run via `daily_startup.py`.
