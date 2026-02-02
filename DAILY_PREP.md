# OpenAlgo Daily Prep & Trading Workflow

This document outlines the standard daily operating procedure for OpenAlgo trading.

## One-Command Startup

The entire daily setup, including cloning/updating repo, purging stale state, logging in, resolving symbols, and running backtests is handled by a single entrypoint:

```bash
python3 daily_startup.py
```

### Options

*   `--backtest`: Run the daily backtest and leaderboard generation after preparation.
*   `--skip-prep`: Skip the preparation step (purge, login, validation) and only run backtests (if combined with `--backtest`) or just exit.

Example:
```bash
python3 daily_startup.py --backtest
```

## Workflow Steps

1.  **Repository Check**: Ensures `openalgo/` directory exists and is valid.
2.  **Daily Prep (`openalgo/scripts/daily_prep.py`)**:
    *   **Purge Stale State**: Deletes old session files, cached instruments (`instruments.csv`), and risk state files.
    *   **Login & Health Check**: Verifies API connectivity and authentication.
    *   **Fetch Instruments**: Downloads fresh master contract list (or generates mocks if API unavailable).
    *   **Symbol Validation**: Iterates through all strategies in `active_strategies.json` and ensures their configured symbols resolve to valid, tradable contracts using `SymbolResolver`.
        *   **NSE Options**: Resolves Weekly/Monthly expiries dynamically.
        *   **MCX**: Auto-detects and prefers MINI contracts (e.g. `SILVERMIC...`).
3.  **Backtest & Leaderboard (`openalgo/scripts/daily_backtest_leaderboard.py`)** (Optional):
    *   Runs base strategies on recent data.
    *   Selects Top 3 performers.
    *   Generates and tests fine-tuned variants.
    *   Outputs `LEADERBOARD.md` and `leaderboard.json`.

## Symbol Configuration

Strategies should use generic configurations. The system automatically resolves them.

**Example `active_strategies.json`:**
```json
{
    "NIFTY_STRATEGY": {
        "underlying": "NIFTY",
        "type": "OPT",
        "expiry_preference": "WEEKLY",
        "option_type": "CE"
    },
    "SILVER_STRATEGY": {
        "underlying": "SILVER",
        "type": "FUT",
        "exchange": "MCX"
    }
}
```

**Resolution Logic:**
*   **NSE Options**: `WEEKLY` picks nearest weekly expiry. `MONTHLY` picks the last expiry of the current month cycle (rolls to next month if current passed).
*   **MCX**: Prefers symbols containing `MINI` or ending in `M`. Fallback to smallest lot size.

## Troubleshooting

*   **Invalid Symbol Error**: Check `active_strategies.json`. Ensure `underlying` matches Exchange Master list names (e.g., `NIFTY 50` vs `NIFTY`).
*   **API Connection Failed**: Check Broker API is running on ports 5001/5002.
*   **Backtest No Data**: Ensure historical data API is accessible or local data is present.

## Logs

*   Startup logs: Console output.
*   Detailed logs: `logs/openalgo.log`.
*   Strategy logs: `openalgo/strategies/logs/`.
