# OpenAlgo Daily Prep & Backtesting Guide

This guide details the daily workflow for ensuring OpenAlgo is ready for trading, verifying symbols, and ranking strategies.

## 1. Daily Preparation

The `daily_startup.py` script is the main entry point for the trading day. It ensures the OpenAlgo repository is present and then executes the preparation workflow.

### Usage
```bash
# Standard Prep
./daily_startup.py

# Prep + Backtest & Leaderboard
./daily_startup.py --backtest
```

### What it does:
1.  **Repository Check**: Checks for `openalgo/` directory.
2.  **Daily Prep**: Launches `openalgo/scripts/daily_prep.py` which:
    *   **Environment Check**: Verifies `OPENALGO_APIKEY` and repo structure.
    *   **Purge Stale State**: Deletes previous day's:
        *   Strategy state files (`openalgo/strategies/state/*.json`)
        *   Cached instruments (`openalgo/data/instruments.csv`)
        *   Session files (Aggressive purge of `openalgo/sessions/`)
    *   **Authentication Check**: Verifies connectivity to Broker (Kite/Dhan) and API accessibility.
    *   **Fetch Instruments**: Downloads the latest instrument list from the broker (or generates a mock list with `lot_size` info if API is unavailable).
    *   **Symbol Validation**: Resolves all strategies in `active_strategies.json` to valid, tradable symbols for *today*.

### Output
The script outputs a validation table. If any strategy has an invalid symbol (e.g., expired option, missing future), the script **exits with an error**, preventing trading.

```
--- SYMBOL VALIDATION REPORT ---
STRATEGY             | TYPE     | INPUT           | RESOLVED                  | STATUS
------------------------------------------------------------------------------------------
ORB_NIFTY            | EQUITY   | NIFTY           | NIFTY                     | ✅ Valid
SuperTrend_NIFTY     | EQUITY   | NIFTY           | NIFTY                     | ✅ Valid
MCX_SILVER           | FUT      | SILVER          | SILVERMIC23NOVFUT         | ✅ Valid
```

## 2. Strategy Configuration

Strategies are defined in `openalgo/strategies/active_strategies.json`.

### Example Config
```json
{
    "ORB_NIFTY": {
        "strategy": "orb_strategy",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE",
        "params": { "quantity": 50 }
    },
    "MCX_SILVER": {
        "strategy": "mcx_commodity_momentum_strategy",
        "underlying": "SILVER",
        "type": "FUT",
        "exchange": "MCX",
        "params": { "quantity": 1 }
    }
}
```

## 3. Symbol Resolver Logic

The `SymbolResolver` (`openalgo/strategies/utils/symbol_resolver.py`) handles dynamic symbol selection.

*   **Equity**: Verifies existence in master list.
*   **Futures (NSE/MCX)**:
    *   Selects the nearest expiry (Active Contract).
    *   **MCX Specific**: Prefers **MINI** contracts by checking:
        1.  Contracts in the same expiration cycle (Month/Year).
        2.  Sorting by `lot_size` ascending (Prefer 1 over 5 over 30).
        3.  Regex fallback ('M' or 'MINI' in symbol).
*   **Options**:
    *   Filters by Underlying, Type (CE/PE).
    *   Selects expiry based on preference (WEEKLY/MONTHLY). Monthly picks the last expiry of the month.
    *   Validates that contracts exist for the target date.

## 4. Daily Backtest & Ranking

To run a simulation backtest of all active strategies and generate a leaderboard:

```bash
./daily_startup.py --backtest
```

This invokes `openalgo/scripts/daily_backtest_leaderboard.py`, which:
1.  **Offline Support**: Uses `LocalBacktestEngine` (via `yfinance`) if the API is unavailable.
2.  **Backtest**: Runs strategies against historical data (default 55 days lookback).
3.  **Fine-Tuning Loop**:
    *   Identifies top strategies.
    *   Generates variants (small parameter tweaks).
    *   Backtests variants to find robust parameters.
4.  **Leaderboard**: Outputs `LEADERBOARD.md` and `leaderboard.json` with metrics (Sharpe, Return, Drawdown).

## 5. Troubleshooting

*   **API Connection Failed**: Ensure the local OpenAlgo server (port 5001/5002) is running.
*   **Invalid Symbol**:
    *   Check `instruments.csv` in `openalgo/data`.
    *   Verify the contract exists (e.g., is today a holiday? did expiry happen yesterday?).
    *   Update `active_strategies.json` if the underlying name changed.
*   **Login Issues**:
    *   The `daily_prep` script purges session state to force a fresh login check.
    *   If login fails, check environment variables `OPENALGO_APIKEY`.
