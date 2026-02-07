# Final Deployment Checklist

## Recommended Strategies

| Strategy | Symbol | Timeframe | Exp. Return | Sharpe | Win Rate |
|---|---|---|---|---|---|
| **AI Hybrid Reversion Breakout** | NIFTY | 15m / Daily | ~4-5% / mo | >3.0 | >80% |
| **Advanced ML Momentum** | NIFTY | 15m / Daily | ~1-2% / mo | >1.5 | ~50% |

## Deployment Rules

### 1. Risk Management
- **Max Risk Per Trade**: 1% - 2% of Capital.
- **Max Portfolio Risk**: 5% Daily Drawdown.
- **Stop Loss**:
    - `ML_Momentum`: 1.5% fixed or 2.0x ATR Trailing.
    - `AI_Hybrid`: 2.0x ATR Stop.
- **Cooldown**: Stop trading for the day if 2 consecutive losses occur in the same strategy.

### 2. Symbol Mapping & Data
- **NSE Equity/Index**:
    - NIFTY -> `NIFTY` (OpenAlgo) -> `^NSEI` (Yahoo Backup).
    - INDIA VIX -> `INDIA VIX` -> `^INDIAVIX`.
- **MCX Commodities**:
    - SILVERMIC -> `SILVERMIC` -> `SI=F` (Global Proxy).
    - **Note**: Ensure `SI=F` data is available or switch to `SILVER.NS` (ETF) for correlation checks if Global Futures are missing.

### 3. Execution & Hygiene
- **Slippage Assumptions**:
    - NSE Liquid: 0.05% (5 bps).
    - MCX: 0.08% (8 bps) due to spread.
- **Timing**:
    - Avoid trading first 15 mins (09:15-09:30) for Momentum unless gap fade.
    - Square off all intraday positions by 15:15 (NSE) / 23:00 (MCX).
- **VIX Filter**:
    - If `INDIA VIX > 25`, reduce position size by 50%.
    - If `INDIA VIX < 12`, tighten stops (volatility compression risk).

### 4. Monitoring
- Run `openalgo/scripts/perform_audit.py` weekly.
- Monitor `openalgo/strategies/logs/` for "Error" or "Warning".
- Verify "Global Alignment" for MCX trades manually if API feels laggy.
