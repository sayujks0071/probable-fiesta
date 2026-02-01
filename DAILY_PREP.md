# OpenAlgo Daily Prep & Trading Workflow

This document outlines the daily preparation routine required to run OpenAlgo strategies safely and effectively. The `daily_prep.py` script acts as the master entry point for the trading day.

## 1. Prerequisites

*   **Repository Path:** Ensure the repository contains the `openalgo` directory at the root (e.g., `./openalgo/`).
*   **Environment Variables:**
    *   `OPENALGO_APIKEY`: Your API Key (defaults to `demo_key` for testing).
    *   `OPENALGO_HOST`: API Host (defaults to `http://127.0.0.1:5001`).

## 2. Running Daily Prep

At the start of every trading day, execute the following command from the repository root:

```bash
python3 openalgo/scripts/daily_prep.py
```

### Command Line Arguments

*   `--skip-backtest`: Skips the daily backtest and leaderboard generation step. Useful for quick restarts during market hours.
*   `--output <dir>`: Directory to save audit reports (default: `openalgo/log/audit_reports`).

## 3. Workflow Steps

The script performs the following actions in order:

1.  **Repo & Env Check:** Verifies the `openalgo` directory exists and required environment variables are set.
2.  **Purge Stale State:**
    *   Deletes previous day's session files (tokens, cookies).
    *   Deletes cached `instruments.csv`.
    *   Clears strategy state files (e.g., `openalgo/strategies/state/*.json`).
3.  **Authentication Health Check:** Runs a script to verify broker connectivity and OpenAlgo login status.
4.  **Refresh Instruments:** Fetches the latest instrument master from the API. If the API is offline, it generates a comprehensive mock list for testing.
5.  **Symbol Validation:**
    *   Resolves symbols for all active strategies in `openalgo/strategies/active_strategies.json`.
    *   **NSE Options:** Auto-selects correct Weekly/Monthly expiry.
    *   **MCX:** Auto-selects **MINI** contracts if available (e.g., `SILVERMIC` over `SILVER`).
    *   **Report:** Prints a table showing Valid/Invalid symbols. **Trading halts if any symbol is invalid.**
6.  **Backtest & Leaderboard (Optional):**
    *   Runs recent history backtests for key strategies.
    *   Generates `leaderboard.json` and `LEADERBOARD.md` in the output directory.
    *   Calculates metrics including Sharpe Ratio, Expectancy, and Time in Market.

## 4. Troubleshooting

### Invalid Symbols
If the validation report shows "🔴 Invalid":
*   Check `openalgo/strategies/active_strategies.json`.
*   Ensure the underlying name matches the broker's master (e.g., `NIFTY 50` vs `NIFTY`).
*   For Options, ensure the expiry preference (WEEKLY/MONTHLY) aligns with available contracts.

### Login Issues
*   If "Authentication check failed", ensure the OpenAlgo API server is running (`port 5001`).
*   Check `logs/openalgo.log` for detailed error messages.

### Backtest Failures
*   Ensure historical data is available. The backtest engine fetches data via the API.
*   Check `openalgo/log/strategies/` for individual strategy logs if needed.

## 5. Output Files

*   **Instruments:** `openalgo/data/instruments.csv`
*   **Leaderboard:** `LEADERBOARD.md` and `leaderboard.json` (in output dir)
*   **Logs:** `logs/openalgo.log`

---
**Safe Trading!**
