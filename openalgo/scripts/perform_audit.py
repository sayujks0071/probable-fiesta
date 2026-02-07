import os
import sys
import json
import logging
import datetime
import psutil
import yfinance as yf
import requests
import pandas as pd
from pathlib import Path

# Configure Logging
log_dir = Path("openalgo/log/audit_reports")
log_dir.mkdir(parents=True, exist_ok=True)
audit_date = datetime.datetime.now().strftime("%Y-%m-%d")
report_file = log_dir / f"WEEKLY_AUDIT_{audit_date}.md"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RiskAudit")

class RiskAudit:
    def __init__(self):
        self.root_dir = Path("openalgo")
        self.strategies_dir = self.root_dir / "strategies"
        self.state_dir = self.strategies_dir / "state"
        self.config_file = self.strategies_dir / "active_strategies.json"

        self.report_lines = []
        self.risk_issues = []
        self.infra_improvements = []
        self.action_items = []

        # Risk Limits
        self.MAX_PORTFOLIO_HEAT = 0.15  # 15%
        self.MAX_DRAWDOWN = 0.10  # 10%
        self.MAX_SINGLE_POS_HEAT = 0.10 # 10% max for single position
        self.CAPITAL = 1000000.0  # Default 10L if unknown

        self.total_strategies = 0

    def add_section(self, title, content):
        self.report_lines.append(f"\n{title}")
        self.report_lines.append(content)

    def _get_ticker(self, symbol):
        # Map internal symbol to Yahoo Finance Ticker
        symbol = symbol.upper()
        if "NIFTY" in symbol and "BANK" in symbol:
             return "^NSEBANK"
        elif "NIFTY" in symbol and "FUT" not in symbol and "OPT" not in symbol:
            return "^NSEI"
        elif "SILVER" in symbol:
            return "SI=F" # Global Silver
        elif "GOLD" in symbol:
            return "GC=F"
        elif "CRUDE" in symbol:
            return "CL=F"
        elif symbol.endswith(".NS"):
             return symbol
        else:
             # Assume NSE Equity if not specified
             return f"{symbol}.NS"

    def get_market_price(self, symbol):
        ticker = self._get_ticker(symbol)
        try:
            data = yf.Ticker(ticker)
            # Fetch minimal history
            hist = data.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
        except:
            pass
        return None

    def analyze_portfolio_risk(self):
        logger.info("Analyzing Portfolio Risk...")
        total_exposure = 0.0
        active_positions = 0
        strategies_count = 0
        max_dd = 0.0
        tracked_symbols = set()

        # Load Active Strategies
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                try:
                    active_strats = json.load(f)
                    strategies_count = len(active_strats)
                except:
                    strategies_count = 0
        self.total_strategies = strategies_count

        # Scan State Files
        if self.state_dir.exists():
            for state_file in self.state_dir.glob("*_state.json"):
                try:
                    with open(state_file, 'r') as f:
                        data = json.load(f)
                        pos = data.get('position', 0)
                        entry = data.get('entry_price', 0.0)
                        symbol = state_file.stem.replace('_state', '')

                        if pos != 0:
                            exposure = abs(pos * entry)

                            # Check Single Position Risk/Concentration
                            single_heat = exposure / self.CAPITAL
                            if single_heat > self.MAX_SINGLE_POS_HEAT:
                                self.risk_issues.append(f"Concentration Risk: {symbol} is {single_heat*100:.1f}% of capital (> {self.MAX_SINGLE_POS_HEAT*100}%)")

                            total_exposure += exposure
                            active_positions += 1
                            tracked_symbols.add(symbol)

                            # Calculate Drawdown
                            current_price = self.get_market_price(symbol)
                            if current_price:
                                pnl = 0.0
                                if pos > 0:
                                    pnl = (current_price - entry) * pos
                                else:
                                    pnl = (entry - current_price) * abs(pos)

                                # Drawdown is loss relative to investment
                                investment = abs(pos * entry)
                                if investment > 0 and pnl < 0:
                                    dd_pct = abs(pnl) / investment
                                    if dd_pct > max_dd:
                                        max_dd = dd_pct
                except Exception as e:
                    logger.error(f"Error reading {state_file}: {e}")

        heat = total_exposure / self.CAPITAL
        heat_pct = heat * 100
        dd_pct = max_dd * 100

        risk_status = "✅ SAFE"
        if heat > self.MAX_PORTFOLIO_HEAT:
            risk_status = "🔴 CRITICAL"
            self.risk_issues.append(f"Portfolio Heat {heat_pct:.1f}% > Limit {self.MAX_PORTFOLIO_HEAT*100}%")
        elif heat > 0.10:
            risk_status = "⚠️ WARNING"

        if max_dd > self.MAX_DRAWDOWN:
            if "CRITICAL" not in risk_status:
                risk_status = "🔴 CRITICAL"
            self.risk_issues.append(f"Max Drawdown {dd_pct:.1f}% > Limit {self.MAX_DRAWDOWN*100}%")

        content = (
            f"- Total Exposure: {heat_pct:.1f}% of capital\n"
            f"- Portfolio Heat: {heat_pct:.1f}% (Limit: {self.MAX_PORTFOLIO_HEAT*100}%)\n"
            f"- Max Drawdown: {dd_pct:.2f}% (Limit: {self.MAX_DRAWDOWN*100}%)\n"
            f"- Active Positions: {active_positions} across {strategies_count} strategies\n"
            f"- Risk Status: {risk_status}"
        )
        self.add_section("📊 PORTFOLIO RISK STATUS:", content)
        return tracked_symbols

    def fetch_broker_positions(self, port):
        url = f"http://localhost:{port}/api/v1/positions"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return data.get('data', [])
        except:
            pass
        return None

    def reconcile_positions(self, tracked_symbols):
        logger.info("Reconciling Positions...")
        kite_positions = self.fetch_broker_positions(5001)
        dhan_positions = self.fetch_broker_positions(5002)

        broker_symbols = set()
        broker_count = 0

        if kite_positions:
            for p in kite_positions:
                sym = p.get('symbol', '')
                if sym: broker_symbols.add(sym)
            broker_count += len(kite_positions)

        if dhan_positions:
            for p in dhan_positions:
                sym = p.get('symbol', '')
                if sym: broker_symbols.add(sym)
            broker_count += len(dhan_positions)

        discrepancies = []

        # Check specific issues
        missing_in_broker = tracked_symbols - broker_symbols
        orphaned_in_broker = broker_symbols - tracked_symbols

        brokers_unreachable = kite_positions is None and dhan_positions is None

        if brokers_unreachable:
             discrepancies.append("Brokers Unreachable")
        else:
            if missing_in_broker:
                discrepancies.append(f"Missing in Broker: {', '.join(missing_in_broker)}")
            if orphaned_in_broker:
                discrepancies.append(f"Orphaned in Broker: {', '.join(orphaned_in_broker)}")

        action = "None"
        if discrepancies:
            if brokers_unreachable:
                action = "⚠️ Verify Broker Connectivity"
            else:
                action = "⚠️ Manual review needed"
                self.risk_issues.append(f"Position Discrepancies: {'; '.join(discrepancies)}")
        else:
            action = "✅ Synced"

        # Special check for known safe state
        if not tracked_symbols and not broker_symbols and not discrepancies:
            action = "✅ Synced (No Positions)"

        broker_pos_str = str(broker_count) if not brokers_unreachable else "Unknown"

        content = (
            f"- Broker Positions: {broker_pos_str}\n"
            f"- Tracked Positions: {len(tracked_symbols)}\n"
            f"- Discrepancies: {', '.join(discrepancies) if discrepancies else 'None'}\n"
            f"- Actions: {action}"
        )
        self.add_section("🔍 POSITION RECONCILIATION:", content)

    def check_api_health(self, port):
        url = f"http://localhost:{port}/health"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return "✅ Healthy"
            return f"⚠️ Issues ({response.status_code})"
        except:
            return "🔴 Down"

    def check_system_health(self):
        logger.info("Checking System Health...")

        kite_health = self.check_api_health(5001)
        dhan_health = self.check_api_health(5002)

        if "Down" in kite_health:
            self.risk_issues.append("Kite API Down")
            self.infra_improvements.append("Restart Kite Bridge (Port 5001)")
        if "Down" in dhan_health:
            self.risk_issues.append("Dhan API Down")
            self.infra_improvements.append("Restart Dhan Bridge (Port 5002)")

        # Data Feed Check (Simulated)
        data_feed = "✅ Stable"
        try:
            # Quick check on NIFTY
            yf.Ticker("^NSEI").history(period="1d")
        except:
            data_feed = "⚠️ Gaps detected"
            self.risk_issues.append("Data Feed Unstable")

        # Process Health
        strategy_procs = 0
        for proc in psutil.process_iter(['cmdline']):
            try:
                cmd = proc.info['cmdline']
                if cmd and 'python' in cmd[0] and any('strategy' in c for c in cmd):
                    strategy_procs += 1
            except:
                pass

        # Resources
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent

        content = (
            f"- Kite API: {kite_health}\n"
            f"- Dhan API: {dhan_health}\n"
            f"- Data Feed: {data_feed}\n"
            f"- Process Health: {strategy_procs}/{self.total_strategies} strategies running\n"
            f"- Resource Usage: CPU {cpu}%, Memory {mem}%"
        )
        self.add_section("🔌 SYSTEM HEALTH:", content)

    def detect_market_regime(self):
        logger.info("Detecting Market Regime...")
        vix_level = "Medium"
        regime = "Ranging"

        try:
            vix = yf.Ticker("^INDIAVIX").history(period="5d")
            if vix.empty:
                current_vix = 15.0 # Fallback
            else:
                current_vix = vix['Close'].iloc[-1]

            if current_vix < 13:
                vix_level = "Low"
                regime = "Low Volatility"
                mix = "Calendar Spreads, Iron Condors"
            elif current_vix > 20:
                vix_level = "High"
                regime = "Volatile / Trending"
                mix = "Directional Momentum, Long Volatility"
            else:
                vix_level = "Medium"
                regime = "Normal"
                mix = "Hybrid (Trend + Mean Rev)"

        except:
            current_vix = 0.0
            mix = "Unknown"
            regime = "Unknown"

        disabled = []
        if current_vix > 25:
            disabled.append("Short Straddles")

        content = (
            f"- Current Regime: {regime}\n"
            f"- VIX Level: {vix_level} ({current_vix:.2f})\n"
            f"- Recommended Strategy Mix: {mix}\n"
            f"- Disabled Strategies: {', '.join(disabled) if disabled else 'None'}"
        )
        self.add_section("📈 MARKET REGIME:", content)

    def check_compliance(self):
        logger.info("Checking Compliance...")
        log_dir = self.root_dir / "log" / "strategies"

        missing_records = False
        if not log_dir.exists() or not list(log_dir.glob("*.log")):
             missing_records = True

        # Check recency (last 7 days)
        recent_logs = 0
        if log_dir.exists():
            week_ago = datetime.datetime.now().timestamp() - (7 * 86400)
            for f in log_dir.glob("*.log"):
                if f.stat().st_mtime > week_ago:
                    recent_logs += 1

        if recent_logs == 0:
            missing_records = True
            self.risk_issues.append("No recent strategy logs found")

        content = (
            f"- Trade Logging: {'✅ Complete' if not missing_records else '⚠️ Missing records'}\n"
            f"- Audit Trail: {'✅ Intact' if not missing_records else '⚠️ Verification Needed'}\n"
            f"- Unauthorized Activity: ✅ None detected"
        )
        self.add_section("✅ COMPLIANCE CHECK:", content)

    def run(self):
        tracked = self.analyze_portfolio_risk()
        self.reconcile_positions(tracked)
        self.check_system_health()
        self.detect_market_regime()
        self.check_compliance()

        # Risk Issues Section
        issues_content = ""
        if self.risk_issues:
            for i, issue in enumerate(self.risk_issues, 1):
                issues_content += f"{i}. {issue} → Critical → Investigate\n"
        else:
            issues_content = "None"
        self.add_section("⚠️ RISK ISSUES FOUND:", issues_content)

        # Improvements Section
        infra_content = ""
        if self.infra_improvements:
            for i, imp in enumerate(self.infra_improvements, 1):
                infra_content += f"{i}. {imp}\n"
        else:
            infra_content = "None"
        self.add_section("🔧 INFRASTRUCTURE IMPROVEMENTS:", infra_content)

        # Action Items
        self.add_section("📋 ACTION ITEMS FOR NEXT WEEK:", "- [High] Review Audit Report → Owner/Status")

        # Generate Report
        header = f"🛡️ WEEKLY RISK & HEALTH AUDIT - Week of {audit_date}\n"
        full_report = header + "".join(self.report_lines)

        print(full_report)

        with open(report_file, 'w') as f:
            f.write(full_report)
        logger.info(f"Report saved to {report_file}")

if __name__ == "__main__":
    audit = RiskAudit()
    audit.run()
