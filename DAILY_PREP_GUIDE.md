# OpenAlgo Daily Prep & Trading Guide

This guide explains the robust daily workflow for OpenAlgo, ensuring symbol validity, clean state, and optimized strategy selection.

## 1. Daily Startup Routine

Run the daily startup script to prepare the environment:

```bash
python3 daily_startup.py --backtest
```

This command performs the following:
1.  **Repository Check**: Ensures `vendor/openalgo` is present and consistent.
2.  **Daily Prep**:
    - Purges stale sessions and state files.
    - Fetches latest instruments (or generates mocks).
    - Validates all strategy symbols using `SymbolResolver`.
    - Generates a validation report.
3.  **Backtest & Optimization** (with `--backtest` flag):
    - Runs all strategies against historical data (mocked via Yahoo Finance).
    - Optimizes top performers by tuning parameters.
    - Generates `LEADERBOARD.md`.

## 2. Symbol Formatting & Resolution

Strategies use a standardized `SymbolResolver` to find tradable instruments.

### Configuration
Strategies are configured in `vendor/openalgo/strategies/active_strategies.json`:

```json
"NIFTY_OPT": {
    "underlying": "NIFTY",
    "type": "OPT",
    "expiry_preference": "WEEKLY",
    "strike_criteria": "ATM",
    "option_type": "CE"
}
```

### Resolution Logic
- **Equities**: Resolves to NSE symbol (e.g., `RELIANCE`).
- **Futures**:
    - **NSE**: Nearest monthly expiry.
    - **MCX**: Prefers `MINI` contracts (e.g., `SILVERMIC...`) or `M` suffix contracts. Fallback to standard.
- **Options**:
    - **Expiry**: `WEEKLY` (nearest) or `MONTHLY` (last expiry of month).
    - **Strike**: `ATM`, `ITM`, `OTM` based on current spot price.

## 3. Troubleshooting

- **"Repo structure invalid"**: Ensure you run `daily_startup.py` from the repo root.
- **"Symbol not found"**: Check `active_strategies.json`. Ensure `underlying` is correct (e.g., `NIFTY` not `NIFTY 50`).
- **"Backtest No Data"**: `MockAPIClient` uses Yahoo Finance. Ensure internet access is available and symbols map correctly (e.g., `SILVER` -> `SI=F`).

## 4. Outputs

- **Validation Report**: Console output during prep.
- **Leaderboard**: `LEADERBOARD.md` generated after backtest.
- **Logs**: `vendor/openalgo/log/` contains strategy logs.
