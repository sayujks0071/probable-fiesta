📊 DAILY AUDIT REPORT - 2026-02-11

🔴 CRITICAL (Fix Immediately):
- [Missing Risk Management] → [openalgo/strategies/scripts/gap_fade_strategy.py] → [Integrate RiskManager class for stop-loss and daily limits]
- [Missing Risk Management] → [openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py] → [Integrate RiskManager class for position sizing and safety checks]
- [Hardcoded Broker Port] → [openalgo/strategies/scripts/gap_fade_strategy.py] → [Use arguments or env vars for port configuration (5001/5002)]

🟡 HIGH PRIORITY (This Week):
- [Import Error Masking] → [openalgo/strategies/scripts/supertrend_vwap_strategy.py] → [Remove broad try-except blocks around imports to expose failures]
- [Code Duplication] → [openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py] → [Refactor manual indicator calculations (ATR, RSI, ADX) to use centralized utility or pandas-ta]

🟢 OPTIMIZATION (Nice to Have):
- [Refactor Indicators] → [openalgo/strategies/utils/trading_utils.py] → [Move calculate_atr/rsi/adx from strategies to shared utility]

💡 NEW STRATEGY PROPOSAL:
- [Adaptive Volatility Skew Strategy] → [Leverage IV Skew (Call vs Put Implied Volatility) to detect market sentiment shifts and execute directional trades with strict RiskManager controls.] → [Implementation Path: openalgo/strategies/scripts/adaptive_volatility_skew.py]

📈 PERFORMANCE INSIGHTS:
- [Log Analysis] → [Logs unavailable or empty. Audit based on code review. Verify logging configuration.]
