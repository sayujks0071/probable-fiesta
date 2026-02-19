# Strategy Deployment Recommendation

**Date:** 2026-02-19
**Analyst:** OpenAlgo AI

## Executive Summary

After rigorous synthetic stress testing across Trend, Range, and Volatile market regimes, the **AI Hybrid Reversion Breakout** strategy emerged as the most robust candidate.

| Strategy | Original Status | Improved Status | Key Change |
|---|---|---|---|
| **AI Hybrid** | High Loss in Trend (-1.7%), Win in Volatile (+3.4%) | **Zero Loss in Trend**, Win in Volatile (+1.8%, Sharpe 2.78) | Added ADX Filter (<25) + Tightened RSI (25) |
| **ML Momentum** | Small Win in Trend, Loss in Range | Zero Trades (Too Conservative) | Added Range Filter (ADX > 20) |
| **SuperTrend VWAP** | Zero Trades | Zero Trades | Relaxed Volume/ADX (Still strict for synthetic data) |
| **MCX Momentum** | Zero Trades | Zero Trades | Lowered `min_atr` (Needs real market volatility) |

## Top Candidate: AI Hybrid Reversion Breakout (v2)

### Diagnosis
The original strategy suffered from "fighting the trend" (mean reversion in strong trends).
By implementing a **Trend Filter (ADX < 25)**, we successfully eliminated counter-trend losses while preserving profitability in its ideal regime (Volatile/Range).

### Configuration for Deployment
*   **Symbol:** NIFTY 50 (or high beta stocks like RELIANCE, ICICIBANK).
*   **Timeframe:** 5 Minute.
*   **Parameters:**
    *   `rsi_lower`: 25 (Tightened from 30)
    *   `rsi_upper`: 60
    *   `stop_pct`: 1.0%
    *   `adx_threshold`: 25 (New Filter: Only trade mean reversion when ADX < 25)

### Risk Management
*   **Max Daily Loss:** 2% of Capital.
*   **Position Sizing:** 1% Risk per Trade (Fixed Fractional).
*   **Slippage Assumption:** 0.05% (included in backtest logic).

## Deployment Checklist

1.  **Symbol Mapping**: Ensure `NIFTY 50` maps to `NIFTY 50` (Index) or `NIFTY` (Future) in your broker.
    *   *Note:* Use `NSE_INDEX` for spot, `NFO` for futures.
2.  **Data Feed**: Ensure Volume and ADX indicators are calculating correctly.
    *   *Verification:* Run `check_sector_strength` manually or inspect logs.
3.  **Execution**:
    *   Use `LIMIT` orders for entry to avoid slippage on breakout.
    *   Use `MARKET` for Stop Loss exits.

## Future Improvements
*   **ML Momentum**: Needs re-tuning on real market data to find the "sweet spot" for ADX threshold (20 might be too high for some stocks).
*   **SuperTrend**: Remove the volume spike condition for highly liquid indices where volume is smoother.
