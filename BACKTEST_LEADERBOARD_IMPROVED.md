# Improved Strategy Leaderboard & Analysis

**Date:** 2026-02-14
**Environment:** Synthetic Data (Trend, Range, Volatile Regimes)

## 1. Leaderboard (Risk-Adjusted)

| Rank | Strategy | Avg Sharpe | Trend Sharpe | Range Sharpe | Volatile Sharpe | Best Variant |
|---|---|---|---|---|---|---|
| 1 | **ML_Momentum** | **19.73** | 56.79 | 2.79 | -0.39 | `threshold=0.01, vol_multiplier=0.5` |
| 2 | **MCX_Momentum** | 10.17 | 28.19 | 0.09 | 2.23 | `adx_threshold=20` |
| 3 | SuperTrend_VWAP | 0.00 | 0.00 | 0.00 | 0.00 | N/A (Conservative) |
| 4 | AI_Hybrid | < -100 | 0.00 | < -100 | **4.26** | `rsi_lower=35` |

---

## 2. Diagnosis & Improvements

### **1. ML Momentum Strategy (Top Pick)**
- **Diagnosis**: Strong performance in trending markets. Previously lacked position sizing and robustness to market breadth.
- **Improvements Implemented**:
    - **Volatility Sizing**: Added ATR-based sizing (Risk 1% per trade).
    - **Market Breadth**: integrated Index Relative Strength check (Stock ROC - Index ROC).
- **Tuning**: Lower `vol_multiplier` (0.5) performed better, indicating stricter volume filtering helps.

### **2. MCX Commodity Momentum**
- **Diagnosis**: Trend follower that suffered in ranging markets.
- **Improvements Implemented**:
    - **Chop Index**: Added `Chop Index < 61.8` filter to avoid entering during consolidation.
    - **Chandelier Exit**: Implemented ATR-based trailing stop (3x ATR) to lock in profits.
- **Result**: Solid performance in Trend, avoided major losses in Range.

### **3. AI Hybrid Reversion/Breakout**
- **Diagnosis**: Suffered from conflicting signals and "catching falling knives" in strong trends. Huge drawdown in Range due to lack of stop loss discipline in original logic.
- **Improvements Implemented**:
    - **Regime Separation**: Enforced **Breakout ONLY** in Trend/Bullish regimes and **Reversion ONLY** in Range (Bandwidth filter).
    - **Risk Cap**: Added strict quantity caps based on price.
- **Result**: Still risky in Range (needs better Mean Reversion logic) but showed promise in Volatile markets (Sharpe 4.26) with relaxed RSI (`35`).

### **4. SuperTrend VWAP**
- **Diagnosis**: Extremely conservative. Returned 0 trades on synthetic data due to strict filters (VIX, Volume Profile).
- **Improvements Implemented**:
    - **Robustness**: Added sanity checks for VIX data.
    - **Exit Logic**: Added explicit `check_exit` with ATR Trailing Stop.
    - **Filters**: Relaxed Volume Spike threshold from 1.5 std to 1.0 std.

---

## 3. Final Deployment Checklist

### **Recommended Strategies for Forward Testing**
1.  **ML_Momentum**: Deploy on NIFTY 50 stocks.
2.  **MCX_Momentum**: Deploy on Gold/Silver/Crude (High Beta).

### **Deployment Config**
- **Risk Management**:
    - Max Risk Per Trade: 1% of Capital.
    - Max Open Positions: 5.
    - Daily Loss Limit: 3% of Capital.
- **Execution**:
    - Slippage Assumption: 0.05% (5 bps).
    - Mode: Paper Trading for 2 weeks.

### **Parameter Grid (Best)**
```json
{
  "ML_Momentum": { "threshold": 0.01, "vol_multiplier": 0.5 },
  "MCX_Momentum": { "adx_threshold": 20, "period_rsi": 14 },
  "AI_Hybrid": { "rsi_lower": 35, "rsi_upper": 60 },
  "SuperTrend_VWAP": { "threshold": 150, "stop_pct": 2.0 }
}
```
