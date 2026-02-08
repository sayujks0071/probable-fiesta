# Strategy Optimization Report

## Leaderboard (Tuned)

| Rank | Strategy | Trades | Sharpe | Return % | Drawdown % | Best Params |
|---|---|---|---|---|---|---|
| 1 | Gap_Fade | 17 | -0.56 | -0.15% | 1.11% | `threshold=0.1`, `atr_mult=0.3` |
| 2 | AI_Hybrid | 1 | 0.00 | -0.95% | 1.24% | (Baseline) |
| 3 | SuperTrend_VWAP | 0 | 0.00 | 0.00% | 0.00% | (All variants) |
| 4 | MCX_Momentum | 0 | 0.00 | 0.00% | 0.00% | (All variants) |

## Diagnosis

1.  **Gap_Fade**:
    - **Performance**: Active but negative (-0.15% return).
    - **Insight**: Fading gaps in the tested period (Dec 2024 - Jan 2025) was unprofitable. This period likely exhibited strong intraday trend continuation after gaps (Momentum) rather than Reversion.
    - **Improvement**: Implemented ATR-based dynamic threshold. Tuning shows lower thresholds (0.3 ATR) generate more trades but still lose.
    - **Recommendation**: Add a **Trend Filter** (e.g. only fade if gap is against HTF trend) or switch to **Gap & Go** (Momentum) for this regime.

2.  **SuperTrend_VWAP**:
    - **Performance**: No trades despite volume mock and parameter relaxation.
    - **Insight**: The combination of `is_above_vwap`, `is_volume_spike` (even at 1.0 sigma), and `is_above_poc` is too restrictive for 60m aggregated data.
    - **Recommendation**: Test with higher resolution data (5m/15m) or remove Volume Profile confirmation for Hourly timeframe.

3.  **MCX_Momentum**:
    - **Performance**: No trades.
    - **Insight**: ADX filters (>15) were not met for Silver in this period on Hourly timeframe.
    - **Recommendation**: Switch to channel breakout or pure price action for Hourly.

## Deployment Checklist

- [ ] **Risk Limits**: Enforce max daily loss of 2% capital.
- [ ] **Symbol Mapping**: Ensure `yfinance` mapping uses correct Futures tickers if available, or reliable Spot data.
- [ ] **Data Resolution**: Strategies like `SuperTrend_VWAP` require 5m/15m data. Do not deploy on Hourly data.
- [ ] **Regime Filter**: `Gap_Fade` requires a "Range" regime detection. Disable in "Trend" days.
