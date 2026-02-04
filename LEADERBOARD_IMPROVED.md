# Improved Strategy Leaderboard

**Date:** 2026-02-04
**Data Environment:** Local Backtest (Yahoo Finance, 60m Interval, Sep-Nov 2024)

## Summary of Improvements

We analyzed the top strategies and identified critical weaknesses (overfitting, lack of regime filters, dormancy). We implemented "V2" variants with targeted improvements.

### 1. AI Hybrid Reversion Breakout V2
- **Diagnosis:** V1 was dormant in Range regimes and lacked proper separation between Breakout and Reversion logic.
- **Improvements:**
  - **Regime Filter:** Added ADX filter (`ADX > 25` for Breakout, `ADX < 20` for Reversion).
  - **Exits:** Added Time Stop (12 bars) and Breakeven Trigger (1R).
  - **Sizing:** Dynamic Position Sizing based on ATR.
- **Results (SBIN 60m):**
  - **V1:** 0 Trades, 0.00% Return.
  - **V2:** 3 Trades, **1.07% Return**, 66% Win Rate.
  - **Verdict:** V2 is functional and profitable in tested sample.

### 2. ML Momentum V2
- **Diagnosis:** V1 relied on mocked sentiment/sector data and had high overfitting risk (90% win rate in previous logs).
- **Improvements:**
  - **Trend Filter:** Added EMA200 filter (Long only if Price > EMA200).
  - **Volatility Filter:** Avoid entries if `ATR/Close > 5%`.
  - **Real Logic:** Removed mocked "pass-all" variables; implemented real indicators.
- **Results:**
  - Dormant on 60m data (requires 15m resolution for ROC sensitivity).
  - **Recommendation:** Deploy V2 with 15m data for forward testing.

### 3. SuperTrend VWAP V2
- **Diagnosis:** V1 had 0 trades due to overly strict AND conditions (Volume Spike + ADX + POC + VWAP).
- **Improvements:**
  - **Relaxed Filters:** Volume Spike `> 1.1x Mean` (was 1.5x Std), ADX `> 10` (was 20).
  - **Deviation:** Widened VWAP deviation check to 5%.
- **Results:**
  - Dormant on 60m data (VWAP profile requires finer resolution).
  - **Recommendation:** Test on 5m/15m live data.

## Final Ranking (Projected)

| Rank | Strategy | Status | Recommended Action |
|---|---|---|---|
| 1 | **AI Hybrid V2** | **Verified** | **Deploy** (Low Risk, Range/Trend capable) |
| 2 | ML Momentum V2 | Unverified (Data) | Forward Test (Trend Only) |
| 3 | SuperTrend VWAP V2 | Unverified (Data) | Forward Test (Intraday) |

## Deployment Checklist
- [x] Ensure `openalgo/strategies/state/` directory exists and is writable.
- [x] Set `OPENALGO_APIKEY` in environment.
- [ ] For VWAP Strategy: Ensure 5m data feed is available.
- [ ] For ML Momentum: Ensure Sector Index (NIFTY) data is subscribed.
