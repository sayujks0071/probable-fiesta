📊 DAILY AUDIT REPORT - 2026-02-12

🔴 CRITICAL (Fix Immediately):
- **Broker Connectivity**: Broker APIs (Kite Port 5001, Dhan Port 5002) are unreachable. Risk of blind trading.
- **Missing Logs**: No strategy logs found in `openalgo/log/strategies/`. Verify logging configuration in `logging_setup.py`.
- **Logic Divergence**: Significant duplication between `run()` (live) and `generate_signal()` (backtest) methods in strategies like `mcx_commodity_momentum_strategy.py`.

🟡 HIGH PRIORITY (This Week):
- **Refactor Strategies**: Continue refactoring strategies to use shared logic (like `analyze_data` introduced in `supertrend_vwap_strategy.py`) to ensure backtest/live consistency.
- **Risk Manager Integration**: Ensure all strategies (e.g., `gap_fade_strategy.py`) use the centralized `RiskManager` class instead of ad-hoc checks.
- **Hardcoded Credentials**: Remove fallback API keys in `mcx_global_arbitrage_strategy.py`.

🟢 OPTIMIZATION (Nice to Have):
- **Symbol Resolver**: Enhance `SymbolResolver` to better handle MCX MINI vs Standard contract selection without forcing MINI.
- **Performance Analysis**: Once logs are available, analyze Time-of-Day performance to optimize entry timing.

💡 NEW STRATEGY PROPOSAL:
- **Statistical Arbitrage (Pairs Trading)**
  - **Rationale**: Market Neutral strategy suitable for the current "Normal Volatility" regime (VIX ~13.63).
  - **Implementation**: `openalgo/strategies/scripts/pairs_trading_stat_arb.py` created.
  - **Features**: Z-Score Entry/Exit, Cointegration Check (via Correlation), RiskManager integration.

📈 PERFORMANCE INSIGHTS:
- **Data Gap**: Unable to perform detailed analysis due to missing logs.
- **Action Item**: Enable `OPENALGO_LOG_JSON=1` and ensure `log_dir` is writable.
