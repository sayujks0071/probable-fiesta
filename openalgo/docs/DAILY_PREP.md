# OpenAlgo Daily Prep & Trading Workflow

This document outlines the daily routine for preparing OpenAlgo for trading, ensuring symbol hygiene, and running backtests.

## 1. Daily Startup Routine

The central entry point is the **Daily Prep** script. This script must be run at the start of every trading day (e.g., via cron at 08:30 IST).

### Command
```bash
python3 openalgo/scripts/daily_prep.py
```

### What it does:
1.  **Environment Checks**: Verifies API Keys and directories.
2.  **Purge Stale State**: Deletes previous day's sessions and instrument cache.
3.  **Fresh Login Check**:
    *   Verifies if OpenAlgo and Broker tokens are valid.
    *   **Fails immediately** if login is required.
    *   Use `openalgo/scripts/authentication_health_check.py` to diagnose login issues.
4.  **Refresh Instruments**:
    *   Fetches fresh `instruments.csv` from the API.
    *   Fails if API is unreachable (unless `--offline` or `--mock` is used).
5.  **Symbol Validation**:
    *   Validates every strategy in `active_strategies.json` against the fresh instruments.
    *   Resolves complex symbols (Options, MCX MINI).
    *   **Halts trading** if any symbol is invalid.

### CLI Options
*   `--mock`: Use mock data (for testing/dev).
*   `--offline`: Skip instrument fetch (use existing file).
*   `--skip-auth`: Skip authentication checks (dev only).

## 2. Symbol Resolution Rules

Strategies now use a centralized `SymbolResolver`.

### MCX Futures
*   **Preference**: Default to **MINI** contracts (`SILVERMIC`, `GOLDM`).
*   **Fallback**: If MINI is not available, select the smallest `lot_size` contract for the nearest expiry.
*   **Logic**: Looks for symbols containing `MINI` or `M` + Digits.

### NSE Options
*   **Expiry**:
    *   `WEEKLY`: Nearest expiry.
    *   `MONTHLY`: Last expiry of the current month cycle. (If today > monthly expiry, rolls to next month).
*   **Strike Selection**:
    *   Strategies specify `strike_criteria` (`ATM`, `ITM`, `OTM`) relative to Spot Price.

## 3. Troubleshooting

### "Authentication Tokens are Invalid"
*   **Action**: Log in to OpenAlgo UI.
*   **Details**: Run `python3 openalgo/scripts/authentication_health_check.py`.

### "API Connection failed"
*   **Action**: Ensure OpenAlgo server is running (`make run` or `python3 app.py`).
*   **Check**: `OPENALGO_HOST` env var.

### "Symbol Validation Failed"
*   **Action**: Check `active_strategies.json`.
*   **Check**: Ensure the `underlying` exists in today's `instruments.csv`.

## 4. Backtesting & Leaderboard

To run the daily backtest and generate a leaderboard:

```bash
python3 openalgo/scripts/daily_backtest_leaderboard.py
```

*   Reads `active_strategies.json`.
*   Generates 3 variants for tunable strategies.
*   Outputs `LEADERBOARD.md` and `leaderboard.json`.
