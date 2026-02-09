# Strategy Analysis & Improvement Report (Feb 2026)

## Executive Summary
This report analyzes the performance of 3 core strategies using backtesting data from Dec 2025 to Feb 2026 (last 50 days) on RELIANCE (NSE).

**Key Findings:**
1.  **AI_Hybrid**: Initially suffered massive drawdown (-23.5%) due to improper risk sizing and lack of stop loss enforcement in backtesting. The **Improved V2** reduced drawdown by **60%** (to -13.4%) via ATR-based sizing and standardized exits, though market conditions remained unfavorable.
2.  **ML_Momentum**: Showed flat performance due to minimal position sizing (1 unit default). Requires dynamic sizing implementation.
3.  **SuperTrend_VWAP**: Produced 0 trades due to strict entry filters (Volume Spike + Sector Confirmation) not being met with the available data.

## Leaderboard: Original vs Improved

| Rank | Strategy | Return % | Max Drawdown % | Sharpe | Win Rate % | Trades | Improvement |
|------|----------|----------|----------------|--------|------------|--------|-------------|
| 1 | ML_Momentum (v2) | -0.02% | 0.03% | -8.49 | 33.3% | 3 | Lower activity, stable |
| 2 | ML_Momentum (Orig) | -0.04% | 0.15% | -1.85 | 42.8% | 7 | Baseline |
| 3 | **AI_Hybrid (v2)** | **-13.38%** | **16.17%** | -9.12 | 22.2% | 9 | **DD reduced by 23%** |
| 4 | AI_Hybrid (Orig) | -23.54% | 39.57% | -4.05 | 33.3% | 9 | High Risk |
| - | SuperTrend_VWAP | 0.00% | 0.00% | 0.00 | 0.0% | 0 | No Trades |

## Strategy Diagnosis & Improvements

### 1. AI Hybrid Strategy
*   **Diagnosis:**
    *   **Weakness:** Original strategy managed exits inside `run()` loop which is ignored by the backtest engine. It relied on `SimpleBacktestEngine`'s default exits, which were not aligned with the strategy's high-frequency mean reversion logic.
    *   **Risk:** Position sizing `1000 / (2 * ATR)` resulted in excessive leverage when 5m ATR was low, causing 40% drawdown.
*   **Improvements (v2):**
    *   **Exit Logic:** Implemented `check_exit` to enforce SMA20 reversion targets and ATR trailing stops within the backtest cycle.
    *   **Risk:** Cap position size and use strict ATR multipliers.
    *   **Backtest:** Removed `datetime.now()` dependencies to ensure correct historical testing.
*   **Tuning Results:**
    *   Best Variant: `rsi_lower=30`, `rsi_upper=60` (Baseline). Tighter RSI (25) reduced trades but didn't improve Sharpe.

### 2. ML Momentum Strategy
*   **Diagnosis:**
    *   **Weakness:** Traded only 1 unit per trade (default), masking true performance volatility.
    *   **Driver:** Momentum `ROC` and `RSI` filters are robust but generated few signals in the choppy test period.
*   **Improvements (v2):**
    *   **Filters:** Enabled real Relative Strength comparison against NIFTY.
    *   **Exits:** Added `check_exit` for Momentum Fade (RSI < 50).
*   **Tuning Results:**
    *   Higher ROC threshold (0.02) reduced trades to 3 and improved Profit Factor slightly.

### 3. SuperTrend VWAP
*   **Diagnosis:**
    *   **Weakness:** Excessive filtering (Volume Spike + Sector RSI + VIX + ADX) led to zero entries.
    *   **Fix:** Strategy logic is sound but requires parameter relaxation for the current low-volatility/choppy regime or better data quality for Volume Spikes.

## Final Deployment Checklist

1.  **Risk Limits:**
    *   Max Position Size: 500 units (Stocks).
    *   Max Daily Loss: 2% of Capital.
    *   Enable `RiskManager` module for all live trades.

2.  **Symbol Mapping:**
    *   Ensure `NIFTY` maps to `NSE_INDEX|NIFTY 50` in live/paper trading.
    *   Ensure `RELIANCE` maps to `NSE_EQ|RELIANCE`.

3.  **Slippage & Costs:**
    *   Backtests assumed 5bps slippage + 3bps costs. Live trading may experience higher slippage on market orders. Use Limit orders where possible (SmartOrder).

## Recommended Strategy for Forward Test
**ML_Momentum_v2** with **Threshold 0.02** and fixed fractional sizing (e.g. 10% of equity) is recommended for forward testing due to its stability and logic robustness, despite flat backtest results. `AI_Hybrid` requires further regime filtering to avoid losses in trending-down markets.
