# OpenAlgo Daily-Ready Trading Workflow

This document outlines the standard daily preparation and trading workflow for the OpenAlgo strategy system.

## 🚀 Daily Startup Routine

The system provides a unified entrypoint to prepare the environment, validate symbols, and optionally run backtests.

### Usage

Run the following command from the repository root:

```bash
python3 daily_startup.py [flags]
```

### Flags

| Flag | Description |
|---|---|
| (None) | Runs standard **Daily Prep** only (Env Check, Purge State, Login Check, Instruments Fetch, Validation). |
| `--backtest` | Runs **Daily Prep** followed by the **Backtest Leaderboard** pipeline. |
| `--tune` | Runs **Fine-Tuning Loop** (requires `--backtest`). Optimizes top strategies. |

### Examples

**Standard Daily Prep (Run before market open):**
```bash
python3 daily_startup.py
```

**Prep + Generate Leaderboard:**
```bash
python3 daily_startup.py --backtest
```

**Full Pipeline (Prep + Backtest + Tune):**
```bash
python3 daily_startup.py --backtest --tune
```

---

## 🛠️ What Happens During Startup?

1.  **Environment Check**: Verifies `OPENALGO_APIKEY` and repository structure.
2.  **Repo Hardening**: Ensures OpenAlgo core is cloned/updated in `vendor/openalgo/`.
3.  **State Purge**: Deletes stale session files (`openalgo/sessions/`) and cached instruments.
4.  **Login Verification**: Connects to the API using your key. Fails immediately if auth is invalid.
5.  **Instrument Refresh**: Fetches fresh `instruments.csv` (NSE Equity/Derivatives + MCX).
6.  **Symbol Validation**:
    *   Iterates through all strategies in `openalgo/strategies/active_strategies.json`.
    *   Resolves abstract configs (e.g. `{"underlying": "NIFTY", "type": "OPT"}`) to tradable symbols.
    *   **HALTS TRADING** if any symbol cannot be resolved (e.g. invalid underlying or missing option chain).

---

## 📝 Symbol Formatting & Resolution Rules

We enforce strict rules to ensure trades are executed on valid, liquid contracts.

### 1. NSE Options
Strategies should use abstract configuration instead of hardcoded symbols:
```json
"NIFTY_STRATEGY": {
    "underlying": "NIFTY",
    "type": "OPT",
    "option_type": "CE",
    "expiry_preference": "WEEKLY",  // or "MONTHLY"
    "strike_criteria": "ATM"        // or "ITM", "OTM"
}
```
*   **Weekly**: Automatically selects the nearest Thursday expiry.
*   **Monthly**: Automatically selects the last Thursday of the current month cycle.

### 2. MCX Futures
We explicitly prefer **MINI** contracts to manage risk.
*   **Logic**: The system sorts valid futures by **Lot Size** (ascending).
*   **Result**: It will pick **MICRO** (e.g. `SILVERMIC...`) or **MINI** (`SILVERM...`) over Standard contracts if available.
*   **Fallback**: If no Mini/Micro is found, it falls back to the Standard contract and logs a warning.

---

## ❓ Troubleshooting

### "Login Required" Error
*   **Cause**: The system could not verify your API Key or the session was invalid.
*   **Fix**:
    1.  Ensure `OPENALGO_APIKEY` is set in your environment.
    2.  If running locally, ensure the OpenAlgo server is running (`make run` or similar).
    3.  Visit the OpenAlgo dashboard to refresh your session/key if needed.

### "Validation Failed" / "Invalid Symbol"
*   **Cause**: A strategy in `active_strategies.json` references an underlying that doesn't exist in the fetched instruments.
*   **Fix**:
    1.  Check `active_strategies.json`.
    2.  Ensure `instruments.csv` was fetched correctly (check logs).
    3.  If trading Options, ensure the market is open or data is available for the requested expiry.

### "Repo not found"
*   **Cause**: You are running the script from outside the root.
*   **Fix**: `cd` to the repository root before running `daily_startup.py`.
