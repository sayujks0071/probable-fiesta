# Improved Strategy Leaderboard

**Date:** 2026-02-13
**Methodology:** Synthetic Data Backtest (Trend & Range Regimes, 300 bars)

## Top Strategies by Regime

### Regime: TREND (Strong Uptrend)

| Rank | Strategy | Variant | Sharpe | Return % | Trades | Drawdown % |
|---|---|---|---|---|---|---|
| 1 | **ML_Momentum** | `thresh=0.01, vol=0.5` | **18.45** | **24.98%** | 42 | 0.92% |
| 2 | ML_Momentum | `thresh=0.01, vol=1.0` | 21.23 | 22.11% | 34 | 0.92% |
| 3 | ML_Momentum | `thresh=0.02, vol=1.0` | 88.96 | 3.85% | 4 | 0.45% |
| 4 | AI_Hybrid | All Variants | 0.00 | 0.00% | 0 | 0.00% |
| 5 | MCX_Momentum | All Variants | 0.00 | 0.00% | 0 | 0.00% |

> **Note:** High Sharpe on Rank 3 is due to low trade count (4). Rank 1 is preferred for robustness.

### Regime: RANGE (Choppy/Sideways)

| Rank | Strategy | Variant | Sharpe | Return % | Trades | Drawdown % |
|---|---|---|---|---|---|---|
| 1 | AI_Hybrid | All Variants | 0.00 | 0.00% | 0 | 0.00% |
| 2 | MCX_Momentum | All Variants | 0.00 | 0.00% | 0 | 0.00% |
| 3 | ML_Momentum | `thresh=0.01, vol=0.5` | -2.52 | -2.10% | 8 | 2.10% |

## Strategy Diagnosis & Improvements

### 1. ML Momentum (Winner)
*   **Diagnosis:** Strong performance in trending markets. Previously prone to overtrading in chop.
*   **Improvements Applied:**
    *   **Trend Filter:** Added Linear Regression Slope check to ensure positive trend structure.
    *   **Exit Logic:** Added RSI < 50 early exit to capture profit before reversal.
    *   **Sizing:** Implemented ATR-based volatility sizing.
*   **Best Variant:** Threshold 0.01, Volume Multiplier 0.5.

### 2. AI Hybrid
*   **Diagnosis:** Intended for both regimes but strict filters prevented trades in short synthetic data.
*   **Improvements Applied:**
    *   **Breakout:** Added ADX > 25 filter to confirm breakout strength.
    *   **Reversion:** Added Green Candle confirmation (Price > Prev Close) to avoid "catching a falling knife".
    *   **Fix:** Corrected ADX calculation logic.

### 3. MCX Momentum
*   **Diagnosis:** Pure trend follower.
*   **Improvements Applied:**
    *   **Chop Filter:** Added explicit `ADX < 20` check to block trades in choppy markets.
    *   **Exit:** Explicit exit signals when momentum fades.

### 4. SuperTrend VWAP
*   **Diagnosis:** Logic was computationally expensive (O(N^2) VWAP calc) causing timeouts in iterative backtest.
*   **Improvements Applied:**
    *   **Optimization:** Replaced expensive `groupby` VWAP with anchored cumulative VWAP for backtesting performance.
    *   **Direction:** Added Short/Sell logic (previously only Long).
    *   **Filter:** Added SuperTrend indicator for trend confirmation.

## Deployment Checklist

### Risk Management
*   [ ] **Max Daily Loss:** Set to 2% of capital (e.g., ₹2,000 for ₹1L account).
*   [ ] **Position Sizing:** Use ATR-based sizing. Max 1-2% risk per trade.
*   [ ] **Max Open Positions:** Limit to 2-3 correlated assets.

### Symbol Selection
*   **Equity:** High beta, liquid stocks (NIFTY 50 top constituents).
*   **MCX:** GOLD, SILVER (High liquidity contracts).

### Execution
*   [ ] **Slippage:** Assume 0.05% slippage in live trading.
*   [ ] **Latency:** Ensure VPS latency < 50ms to broker.
*   [ ] **Market Hours:** 09:15 - 15:30 (NSE), 09:00 - 23:30 (MCX).

### Parameter Settings (Recommended)
*   **ML Momentum:** `threshold=0.01`, `stop_pct=1.0`, `vol_multiplier=0.5`.
*   **AI Hybrid:** `rsi_lower=30`, `rsi_upper=60`.
*   **MCX Momentum:** `adx_threshold=20`, `period_rsi=14`.
