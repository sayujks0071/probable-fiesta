📊 DAILY AUDIT REPORT - 2026-02-13

🔴 CRITICAL (Fix Immediately):
- [Missing Risk Manager] → `mcx_commodity_momentum_strategy.py` → [Fixed] Integrated `RiskManager` for entry validation and stop enforcement.
- [Missing Risk Manager] → `supertrend_vwap_strategy.py` → [Fixed] Integrated `RiskManager` for entry validation and stop enforcement.
- [Logic Error] → `supertrend_vwap_strategy.py` → [Fixed] Resolved `KeyError: 'ema200'` by accessing Series correctly after assignment.

🟡 HIGH PRIORITY (This Week):
- [Portfolio Heat > 15%] → Global → Strategies now enforce `RiskManager.can_trade()` which checks daily loss limits.
- [Concentration Risk] → `supertrend_vwap_strategy.py` → Reduce position sizes or diversify symbols (Risk Manager now active).

🟢 OPTIMIZATION (Nice to Have):
- [Backtest Performance] → `mcx_commodity_momentum_strategy.py` → [Implemented] Module-level caching for strategy instance in `generate_signal`.
- [Backtest Performance] → `supertrend_vwap_strategy.py` → [Implemented] Module-level caching for strategy instance in `generate_signal`.

💡 NEW STRATEGY PROPOSAL:
- [DynamicRiskReversion] → [Mean Reversion with Risk-Based Sizing] → `openalgo/strategies/scripts/dynamic_risk_reversion.py`
  - *Rationale*: Addresses portfolio heat issues by dynamically reducing position size when daily PnL is negative.
  - *Implementation*: Uses Bollinger Bands + RSI for signals and `RiskManager.daily_pnl` for sizing.

📈 PERFORMANCE INSIGHTS:
- [High Portfolio Heat (567%)] → Previous audit showed excessive leverage. `RiskManager` integration is now mandatory.
- [Sector Concentration] → Heavy exposure to Energy and Financials. Recommend diversifying with `DynamicRiskReversion` on other sectors.
- [Orphaned Positions] → Audit found positions without strategy tracking. Ensure `RiskManager` state is persisted and checked on startup.
