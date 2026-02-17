# Strategy Leaderboard
**Date:** 2026-02-17
**Backtest:** Synthetic Data (45 Days, 15m)

## Summary
The leaderboard reflects performance on a 45-day synthetic data set (Trend + Chop + Volatile regimes).
**Note:** `SuperTrend_VWAP` requires real market data (Volume Profile) and did not generate trades in this simulation.

| Rank | Strategy | Sharpe | Return % | Drawdown % | Win Rate % | Trades | Key Params |
|---|---|---|---|---|---|---|---|
| 1 | **MCX_Momentum** | -0.64 | -3.75% | 9.75% | 50.00% | 130 | `adx_threshold: 30`, `sma_period: 50` |
| 2 | **ML_Momentum** | -6.47 | -3.65% | 4.05% | 34.78% | 46 | `sma_period: 200`, `vol_multiplier: 0.5` |
| 3 | **AI_Hybrid** | -6.72 | -8.23% | 9.88% | 37.04% | 27 | `rsi_lower: 30`, `rsi_upper: 60`, `adx_filter: True` |
| 4 | **SuperTrend_VWAP** | 0.00 | 0.00% | 0.00% | 0.00% | 0 | `vol_multiplier: 1.0`, `poc_filter: False` |

## Deployment Recommendations
1. **MCX_Momentum:** Deploy with **ADX > 30** filter to avoid chop.
2. **AI_Hybrid:** Critical to use **ADX Regime Filter** (Reversion only if ADX < 25) to prevent large drawdowns.
3. **ML_Momentum:** Use **ATR Trailing Stop** logic (integrated) for better risk management.

## Next Steps
- Validate `SuperTrend_VWAP` with real historical data.
- Monitor `MCX_Momentum` slippage in live trading (high frequency).
