# OpenAlgo Daily Workflow

This document outlines the standard daily preparation and trading workflow.

## Entrypoint

Use the `daily_start.sh` script to prepare the environment for trading.

```bash
./daily_start.sh
```

To run an optional backtest pipeline after preparation:

```bash
./daily_start.sh --backtest
```

## What it does

1.  **Environment Setup** (`tools/setup_env.py`):
    *   Verifies that `openalgo` repo is present.
    *   Ensures `PYTHONPATH` includes the repository root.

2.  **Daily Preparation** (`openalgo/scripts/daily_prep.py`):
    *   **Environment Check**: Validates API Keys and Timezone.
    *   **Purge**: Deletes stale session files and old instruments.
    *   **Auth Check**: Verifies connectivity to Broker and OpenAlgo services.
    *   **Instrument Fetch**: Downloads latest instruments from API (NSE, NFO, MCX).
    *   **Symbol Validation**:
        *   Iterates through all strategies in `active_strategies.json`.
        *   Resolves symbols using `SymbolResolver` (Supports NSE Options & MCX MINI preference).
        *   Generates `daily_validation_report.md`.
        *   **Stops execution** if any strategy has an invalid symbol.

3.  **Backtest Leaderboard** (Optional) (`openalgo/scripts/daily_backtest_leaderboard.py`):
    *   Loads active strategies.
    *   Resolves symbols using the fresh instrument list.
    *   Runs backtests on recent data (last 5 days).
    *   Generates `LEADERBOARD.md`.

## Symbol Resolution Logic

The system uses a robust `SymbolResolver` (`openalgo/strategies/utils/symbol_resolver.py`):

*   **MCX**: Automatically prefers **MINI** contracts (e.g. `SILVERMIC`) if the underlying is generic (e.g. `SILVER`), unless unavailable.
*   **NSE Options**:
    *   Strictly respects `expiry_preference` (WEEKLY vs MONTHLY).
    *   Selects strikes dynamically (ATM, ITM, OTM).
*   **Validation**: Fails fast if a symbol is not found in the daily master.

## Troubleshooting

*   **Auth Failed**: Run `./openalgo/scripts/authentication_health_check.py` manually to diagnose.
*   **Symbol Invalid**: Check `daily_validation_report.md` for specific errors. Ensure `active_strategies.json` has correct `underlying` names.
*   **No Instruments**: Ensure the OpenAlgo server is running and accessible. Use `--mock` flag with `daily_prep.py` for offline testing.
