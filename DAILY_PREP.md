# Daily Trading Preparation & Safety Workflow

This document outlines the mandatory daily preparation steps, safety guardrails, and symbol resolution logic implemented in OpenAlgo.

## 1. Daily Startup Routine

All trading operations must begin with the `daily_startup.py` script. This script enforces a clean state and validates the environment.

**Command:**
```bash
python3 daily_startup.py
```
*Optional: Add `--backtest` to run the backtest leaderboard after prep.*

**What it does:**
1.  **Repo Check**: Ensures `vendor/openalgo` exists and is up to date.
2.  **State Purge**: Deletes previous day's session tokens, cached instruments, and state files.
3.  **Auth Check**: Verifies Broker and DB connectivity. Fails if critical issues are found.
4.  **Instrument Fetch**: Downloads latest Master Contract Note (NSE/MCX).
5.  **Symbol Validation**: Resolves all configured strategies' symbols to valid tradable contracts.
6.  **Success Marker**: Creates `vendor/daily_prep_passed.json`.

## 2. Safety Guardrails

### Daily Prep Lock
*   Every strategy script checks for the existence of `vendor/daily_prep_passed.json` on startup.
*   If missing, the strategy **halts immediately** (exit code 1).
*   This prevents trading with stale data or unverified environments.

### Authentication Health
*   The system checks for "System Ready" status from `authentication_health_check.py`.
*   If critical issues (e.g., Expired Token, DB Error) are detected, the prep sequence aborts.

## 3. Symbol Resolution

Strategies no longer hardcode symbols. They use the `SymbolResolver` to dynamically select the best contract.

### NSE Options
*   **Weekly**: Selects the nearest weekly expiry.
*   **Monthly**: Selects the monthly contract (last expiry of the current month cycle).
*   **Strike Selection**: Dynamic ATM/ITM/OTM selection based on spot price.

### MCX Futures
*   **MINI Preference**: Automatically prefers `MINI` contracts (e.g., `SILVERM`, `GOLDM`) if available in the front month.
*   **Logic**: Checks for 'M' suffix or 'MINI' in symbol name and validates against lot size.
*   **Fallback**: If no MINI is found, defaults to the standard contract.

## 4. Backtesting & Tuning

The `daily_backtest_leaderboard.py` script runs a daily simulation on recent data.

*   **Tuning**: Automatically generates variants (e.g., different RSI thresholds) for top strategies.
*   **Ranking**: Ranks strategies by Sharpe Ratio and Return.
*   **Output**: `LEADERBOARD.md` and `leaderboard.json`.

## 5. Troubleshooting

*   **"Daily Prep NOT complete"**: Run `python3 daily_startup.py`.
*   **"Authentication check failed"**: Check `logs/openalgo.log` and verify API keys in `.env`.
*   **"Invalid Symbol"**: Check `instruments.csv` or `SymbolResolver` logic for the specific underlying.
