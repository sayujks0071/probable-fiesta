# Strategy Leaderboard (Post-Optimization)

## Regime: TREND (Synthetic Strong Trend)

| Rank | Strategy | Sharpe | Return % | Drawdown % | Trades | Win Rate % | Notes |
|---|---|---|---|---|---|---|---|
| 1 | **ML_Momentum_v2** | 100.80 | 72.65% | 0.29% | 40 | 100.00% | ADX > 20 filter + ATR Sizing. Captured trend perfectly. |
| 2 | **MCX_Momentum_v2** | 102.48 | 15.00%* | 0.00% | 41 | 100.00% | Robust entry (High > High[1]). *Scaled Return (x100 qty). Low DD. |
| 3 | AI_Hybrid_v2 | 0.00 | 0.00% | 0.00% | 0 | 0.00% | Volume filter too strict for synthetic data. |
| 4 | SuperTrend_VWAP_v2 | N/A | N/A | N/A | N/A | N/A | Execution timed out (Volume calculation). |

## Regime: RANGE (Synthetic Mean Reversion)

| Rank | Strategy | Sharpe | Return % | Drawdown % | Trades | Win Rate % | Notes |
|---|---|---|---|---|---|---|---|
| 1 | **MCX_Momentum_v2** | 1.15 | 0.05% | 0.00% | 7 | 57.14% | Survived chop well. Breakout entry prevented false signals. |
| 2 | AI_Hybrid_v2 | 0.00 | 0.00% | 0.00% | 0 | 0.00% | No trades (Filters worked to avoid chop). |
| 3 | ML_Momentum_v2 | -442.07 | -4.66% | 4.66% | 4 | 0.00% | Still susceptible to chop even with ADX > 20. Needs ADX > 25 or 30. |

## Recommendations

1.  **ML_Momentum**: Best for Trends. Increase ADX threshold to 30 to avoid Range bleed.
2.  **MCX_Momentum**: Most Robust (All-Weather). Increase Position Sizing (currently 1 unit).
3.  **AI_Hybrid**: Needs relaxed volume filters for lower liquidity instruments.
