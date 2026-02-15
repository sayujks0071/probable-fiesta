🛡️ WEEKLY RISK & HEALTH AUDIT - Week of 2026-02-15

📊 PORTFOLIO RISK STATUS:- Total Exposure: 50.0% of capital (500,000.00 / 1,000,000)
- Portfolio Heat: 50.0% (Limit: 15.0%)
- Max Drawdown: 0.00% (Limit: 10.0%)
- Active Positions: 1 across 4 strategies
- Risk Status: 🔴 CRITICAL - Heat Limit Exceeded

🔍 POSITION RECONCILIATION:- Broker Positions: Unknown
- Tracked Positions: 1
- Discrepancies: Brokers Unreachable - Cannot Reconcile
- Actions: ⚠️ Verify Broker Connectivity
🔌 SYSTEM HEALTH:- Kite API: 🔴 Down / Unreachable
- Dhan API: 🔴 Down / Unreachable
- Data Feed: ✅ Stable
- Process Health: 0 strategies running
- Resource Usage: CPU 1.2%, Memory 6.2%
- API Errors (Last 7d): 1
- Risk Rejections: 1
📈 MARKET REGIME:- Current Regime: Normal Volatility
- VIX Level: 13.29
- Recommended Strategy Mix: Hybrid (Trend + Mean Rev)
- Disabled Strategies: None
✅ COMPLIANCE CHECK:- Trade Logging: ✅ Active Logs Found (1 active files)
- Audit Trail: ✅ Intact
- Unauthorized Activity: ✅ None detected
⚠️ RISK ISSUES FOUND:1. High Single Position Exposure: mock_strat (50.0%) → Warning → Investigate
2. Circuit Breaker Active: mock_strat_risk_state → Warning → Investigate
3. Trade Risk Exceeded: MOCK_SYMBOL (5.00% > 2.0%) → Warning → Investigate
4. Portfolio Heat 50.0% > Limit 15.0% → Critical → Investigate
5. Broker APIs Unreachable - Position Blind Spot → Warning → Investigate

🔧 INFRASTRUCTURE IMPROVEMENTS:1. Restart Kite Bridge Service (Port 5001)
2. Restart Dhan Bridge Service (Port 5002)

📋 ACTION ITEMS FOR NEXT WEEK:- [Critical] Reduce Portfolio Exposure immediately -> Risk Manager
- [High] Fix Kite API Connectivity -> DevOps
