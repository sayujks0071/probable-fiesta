# OpenAlgo Daily Preparation & Trading Workflow

This guide documents the automated daily routine for preparing OpenAlgo for live trading, ensuring symbol hygiene, and running pre-market validations.

## 🚀 Daily Startup Routine

The entry point for the daily workflow is `daily_startup.py` in the repository root.

```bash
# Run Daily Prep (Purge, Login, Instruments, Validation)
python3 daily_startup.py

# Run Daily Prep + Backtest Leaderboard
python3 daily_startup.py --backtest
```

### Steps Executed:

1.  **Environment Check**: Verifies API keys and paths.
2.  **Purge Stale State**: Deletes previous day's session files, cached instruments, and temporary state to ensure a fresh start.
3.  **Authentication**: Checks/Refreshes login session.
4.  **Fetch Instruments**: Downloads the latest `instruments.csv` from the broker API.
5.  **Symbol Validation**: Resolves and validates trading symbols for all active strategies.
    *   **Exit Criteria**: If ANY symbol is invalid/expired, the script EXITS with an error. Trading is halted.
6.  **Backtest Leaderboard** (Optional): Runs backtests on key strategies using the resolved symbols and generates a performance report.

## 🔍 Symbol Resolution Logic

The system uses a centralized `SymbolResolver` to ensure consistent and safe symbol selection.

### 1. NSE Equities
*   Validates existence in the master instrument list.
*   Auto-corrects common variations (e.g., handles `NIFTY 50` vs `NIFTY`).

### 2. NSE Options
*   **Expiry Selection**:
    *   `WEEKLY`: Selects the *nearest* expiry (this Thursday or next).
    *   `MONTHLY`: Selects the *last* expiry of the current month cycle.
*   **Strike Selection**: Can resolve ATM, ITM, or OTM strikes based on spot price.

### 3. MCX Commodities (Futures)
*   **MINI Preference**: The resolver automatically prioritizes smaller contracts to manage risk.
    *   **Priority 1**: Micro Contracts (`MIC` suffix, Lot Size ~1).
    *   **Priority 2**: Mini Contracts (`M` suffix or `MINI`, Lot Size ~5-10).
    *   **Priority 3**: Standard Contracts (Large Lot Size).
*   **Logic**: It sorts all available futures for the underlying by `Expiry` (nearest first) and then `Lot Size` (smallest first).

### 4. Validation Report
A report is printed to console and resolved symbols are saved to `openalgo/strategies/state/daily_symbol_map.json`.

```text
--- SYMBOL VALIDATION REPORT ---
STRATEGY                  | TYPE     | INPUT           | RESOLVED                       | STATUS
-----------------------------------------------------------------------------------------------
ORB_NIFTY                 | EQUITY   | NIFTY           | NIFTY                          | ✅ Valid
MCX_SILVER                | FUT      | SILVER          | SILVERM27FEB26FUT              | ✅ Valid
...
```

## 📊 Backtest Leaderboard

The backtest pipeline runs strategies against recent data (e.g., last 3-5 days) to ensure they are picking up valid signals.

*   **Output**: `openalgo/reports/LEADERBOARD.md` and `leaderboard.json`.
*   **Metrics**: Sharpe Ratio, Return %, Drawdown, Win Rate.

## 🛠 Troubleshooting

**Issue: "Invalid Symbol" or "Symbol not found"**
1.  Check if `instruments.csv` was downloaded correctly (check `openalgo/data/`).
2.  If using MCX, ensure the contract (Mini/Micro) actually exists for the current expiry. The resolver falls back to Standard if Mini is missing.
3.  Run `python3 openalgo/scripts/daily_prep.py` manually to see verbose output.

**Issue: "Connection Refused"**
1.  Ensure the OpenAlgo API server (Broker Bridge) is running on port 5001.
2.  Check `logs/openalgo.log` for connection errors.

**Issue: "Login Failed"**
1.  The system purges sessions daily. You may need to perform a manual login if the automated flow fails (e.g., OTP requirement).
2.  Check `openalgo/scripts/authentication_health_check.py`.
