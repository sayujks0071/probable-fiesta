# Final Strategy Optimization Report

## 1. Updated Leaderboard (Synthetic Regimes)

**Date:** 2026-02-11

| Rank | Strategy | Avg Sharpe | Trend Return | Range Return | Best Params |
|---|---|---|---|---|---|
| **1** | **MCX_Momentum_v1** | **4.37** | **12.65%** | **4.32%** | ADX>20, SMA Filter=Off |
| 2 | MCX_Momentum_v2 | 4.05 | 10.25% | 4.32% | ADX>20, SMA Filter=50 |
| 3 | MCX_Momentum_v3 | 1.14 | 8.60% | -0.15% | ADX>25, SMA Filter=Off |
| 4 | MCX_Momentum_v4 | 0.73 | 5.81% | -0.15% | ADX>25, SMA Filter=50 |
| 5 | AI_Hybrid (All) | 0.00 | 0.00% | 0.00% | (No Trades - Requires Higher Volatility) |
| 6 | ML_Momentum (All) | -4.65 | -0.01% | -0.12% | (Poor Performance without External Filters) |

## 2. Strategy Diagnosis & Improvements

### A. MCX_Momentum (Winner)
*   **Diagnosis:** Strong performance in trending regimes. The ADX filter successfully identifies high-probability moves.
*   **Improvements Implemented:**
    *   **Trend Filter:** Added SMA50 filter. (Backtest showed `Off` was slightly better for raw return, but `On` reduced drawdown in some scenarios).
    *   **ATR Sizing:** Implemented dynamic position sizing based on Volatility (1% Risk).
*   **Recommended Config:** `ADX Threshold: 20`, `Trend Filter: Optional (Off for aggressive, On for conservative)`.

### B. ML_Momentum
*   **Diagnosis:** Heavily reliant on external factors (Sector, Relative Strength) which were disabled/mocked in synthetic testing. Core momentum logic (ROC + RSI) struggled in pure price action tests.
*   **Improvements Implemented:**
    *   Added `use_filters` toggle to allow pure price-action testing.
    *   Added `ATR` based stop loss.
*   **Recommendation:** Do not deploy standalone without external data feeds (NIFTY/Sector indices).

### C. AI_Hybrid
*   **Diagnosis:** Failed to trigger trades in low-volatility synthetic data. It requires extreme RSI readings (<30/>70) and ADX regime switches.
*   **Improvements Implemented:**
    *   **Regime Switch:** ADX-based switching between Breakout and Reversion logic.
*   **Recommendation:** Needs calibration to lower volatility environments (e.g., RSI 40/60) or deployment only on high-beta assets.

## 3. Deployment Checklist

### Risk Limits
*   **Max Daily Loss:** 2% of Capital.
*   **Max Open Positions:** 3 (to avoid correlation risk).
*   **Position Sizing:** 1% Risk per Trade (using ATR-based SL).

### Symbol Mapping
*   **NSE:** Ensure symbols are liquid (NIFTY 50 universe).
*   **MCX:** Use `FUT` contracts. Map `GOLD` -> `GOLDM...FUT`.

### Slippage Assumptions
*   **Backtest:** 5 bps slippage + 3 bps transaction costs used.
*   **Live:** Monitor execution. If slippage > 10 bps consistently, switch to Limit orders.

### Final Recommendation
Deploy **MCX_Momentum_v1** (ADX>20) on MCX Commodities (Gold/Silver) and high-beta NSE stocks. Monitor AI_Hybrid in paper trading with relaxed thresholds.
