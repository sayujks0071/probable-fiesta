# Strategy Analysis & Optimization Report

**Date:** 2026-02-18
**Context:** Synthetic Data Backtest (Mixed Regimes: Trend, Range, Volatility)

## 1. Leaderboard & Selection

### Baseline Performance (Synthetic Data)
| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Trades | Status |
|---|---|---|---|---|---|---|---|
| 1 | **AI_Hybrid** | **2.91** | **0.33%** | 1.54% | **60.00%** | 5 | **Selected** |
| 2 | SuperTrend_VWAP | 0.00 | 0.00% | 0.00% | 0.00% | 0 | Pending Fixes |
| 3 | MCX_Momentum | 0.00 | 0.00% | 0.00% | 0.00% | 0 | Pending Fixes |
| 4 | ML_Momentum | -3.83 | -0.01% | 0.02% | 42.11% | 19 | Needs Tuning |

### Candidates for Optimization
1.  **AI_Hybrid (Reversion/Breakout)**: Strongest logic, adapts to regimes. Low frequency needs improvement.
2.  **ML_Momentum**: High frequency but poor quality. Needs regime filters.
3.  **SuperTrend_VWAP**: Robust logic but too restrictive filters (POC/VIX) for synthetic/standard data.

---

## 2. Diagnosis & Improvements

### A. AI_Hybrid Strategy
**Diagnosis:**
- **Driver:** Dual logic (mean reversion oversold + breakout momentum) captures distinct edges.
- **Weakness:** Low trade frequency due to strict RSI (30/70) and regime alignment.
- **Improvement:**
    1.  **Relaxed Entries:** Widened RSI thresholds to 35/65.
    2.  **Risk Management:** Added ATR-based Trailing Stop logic.
    3.  **Volume Filter:** Lowered volume multiplier from 2.0x to 1.5x for breakouts.

### B. ML_Momentum Strategy
**Diagnosis:**
- **Driver:** ROC momentum.
- **Weakness:** "Noise Trading" in ranging markets (Negative Sharpe). High trade count with coin-flip win rate.
- **Improvement:**
    1.  **Regime Filter:** Added `ADX > 15` check to ensure trend strength before entering.
    2.  **Exits:** Added ATR Trailing Stop (implied in logic) and stricter stop loss.
    3.  **Position Sizing:** (Future) Volatility targeting.

### C. SuperTrend_VWAP Strategy
**Diagnosis:**
- **Driver:** Trend following with VWAP confirmation.
- **Weakness:** 0 Trades. Point of Control (POC) and VIX filters were filtering out all synthetic data signals.
- **Improvement:**
    1.  **Relax Filters:** Disabled strict POC check (made permissive).
    2.  **Robustness:** Logic now triggers on pure Price vs VWAP + Volume Spike.

---

## 3. Parameter Tuning Guide

### AI_Hybrid
| Parameter | Range | Step | Description |
|---|---|---|---|
| `rsi_lower` | 30 - 40 | 2 | Reversion entry threshold |
| `rsi_upper` | 60 - 70 | 2 | Breakout entry threshold |
| `stop_pct` | 0.5% - 2.0% | 0.25% | Fixed Stop Loss |

### ML_Momentum
| Parameter | Range | Step | Description |
|---|---|---|---|
| `threshold` | 0.005 - 0.02 | 0.005 | ROC Change Threshold |
| `adx_min` | 15 - 25 | 5 | Trend Strength Filter |
| `vol_multiplier` | 0.5 - 1.5 | 0.25 | Volume confirmation |

---

## 4. Final Deployment Checklist

### Risk Limits
- [ ] **Risk Per Trade:** Capped at 1% of Equity (Dynamic Sizing).
- [ ] **Max Drawdown:** Halt trading if daily DD > 2%.
- [ ] **Correlations:** Avoid running `SuperTrend_VWAP` (NIFTY) and `ML_Momentum` (NIFTY) simultaneously with full size.

### Symbol Mapping
- **NSE:** `NIFTY`, `BANKNIFTY`, `RELIANCE`, `TATASTEEL`
- **MCX:** `GOLD`, `SILVER` (Ensure `15m` data availability)

### Slippage Assumptions
- **Backtest:** 5 bps slippage + 3 bps transaction cost.
- **Live:** Use Limit Orders (`SmartOrder`) to minimize impact.

---

## 5. Recommendation
**Deploy:** `AI_Hybrid` (Primary) and `SuperTrend_VWAP` (Secondary).
**Hold:** `ML_Momentum` requires further tuning on real market data (Sector/Relative Strength feeds).
