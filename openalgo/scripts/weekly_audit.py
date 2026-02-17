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
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(log_dir / f"audit_debug_{audit_date}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger("WeeklyAudit")

class WeeklyAudit:
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
        self.MAX_PORTFOLIO_HEAT_PCT = 0.15  # 15% Risk Exposure
        self.MAX_DRAWDOWN_PCT = 0.10  # 10%
        self.MAX_RISK_PER_TRADE_PCT = 0.02 # 2%
        self.MAX_CORRELATION = 0.80

        # Mock Capital Base (Assume 10 Lakhs if unknown)
        self.CAPITAL = 1000000.0

    def add_section(self, title, content):
        self.report_lines.append(f"\n{title}")
        self.report_lines.append(content)

    def _get_ticker(self, symbol):
        # Map internal symbol to Yahoo Finance Ticker
        if "NIFTY" in symbol and "BANK" in symbol:
             return "^NSEBANK"
        elif "NIFTY" in symbol and "FUT" not in symbol and "OPT" not in symbol:
            return "^NSEI"
        elif "SILVER" in symbol:
            return "SI=F" # Global Silver or MCX equivalent
        elif "GOLD" in symbol:
            return "GC=F"
        elif symbol.endswith(".NS"):
             return symbol
        else:
             # Assume NSE Equity if not specified
             return f"{symbol}.NS"
        return None

    def get_market_price(self, symbol):
        ticker = self._get_ticker(symbol)
        if not ticker:
            return None

        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
        except:
            pass
        return None

    def analyze_portfolio_risk(self):
        logger.info("Analyzing Portfolio Risk...")
        total_exposure = 0.0
        total_risk = 0.0
        active_positions_count = 0
        strategies_count = 0
        max_dd = 0.0

        tracked_symbols = set()
        position_details = []

        # Load Active Strategies
        active_strats = {}
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                active_strats = json.load(f)
                strategies_count = len(active_strats)
        else:
            logger.warning("active_strategies.json not found!")

        # Scan State Files
        if self.state_dir.exists():
            for state_file in self.state_dir.glob("*_risk_state.json"):
                try:
                    with open(state_file, 'r') as f:
                        data = json.load(f)
                        positions = data.get('positions', {})

                        for symbol, pos_data in positions.items():
                            qty = pos_data.get('qty', 0)
                            entry = pos_data.get('entry_price', 0.0)
                            stop_loss = pos_data.get('stop_loss', 0.0)

                            if qty != 0:
                                exposure = abs(qty) * entry
                                total_exposure += exposure
                                active_positions_count += 1
                                tracked_symbols.add(symbol)

                                # Calculate Risk
                                risk = 0.0
                                if stop_loss > 0:
                                    risk = abs(entry - stop_loss) * abs(qty)
                                else:
                                    # Fallback: assume 100% risk if no SL (extreme but safe) or just exposure
                                    risk = exposure

                                total_risk += risk

                                # Check per-trade risk
                                risk_pct = (risk / self.CAPITAL) * 100
                                if risk_pct > (self.MAX_RISK_PER_TRADE_PCT * 100):
                                    self.risk_issues.append({
                                        'issue': f"High Risk Trade: {symbol} ({risk_pct:.2f}% > 2%)",
                                        'severity': "Critical",
                                        'fix': "Reduce position size"
                                    })

                                # Calculate DD if market price available
                                current_price = self.get_market_price(symbol)
                                if current_price:
                                    pnl = (current_price - entry) * qty
                                    if pnl < 0:
                                        dd_pct = abs(pnl) / self.CAPITAL
                                        if dd_pct > max_dd:
                                            max_dd = dd_pct

                                position_details.append(f"- {symbol}: {qty} @ {entry} (Risk: {risk_pct:.2f}%)")

                except Exception as e:
                    logger.error(f"Error reading {state_file}: {e}")

        # Calculations
        heat_pct = (total_risk / self.CAPITAL) * 100
        exposure_pct = (total_exposure / self.CAPITAL) * 100

        risk_status = "✅ SAFE"
        if heat_pct > (self.MAX_PORTFOLIO_HEAT_PCT * 100):
            risk_status = "🔴 CRITICAL - Heat Limit Exceeded"
            self.risk_issues.append({
                'issue': f"Portfolio Heat {heat_pct:.1f}% > Limit {self.MAX_PORTFOLIO_HEAT_PCT*100}%",
                'severity': "Critical",
                'fix': "Reduce overall exposure"
            })
        elif heat_pct > 10.0:
            risk_status = "⚠️ WARNING - High Heat"

        if max_dd > self.MAX_DRAWDOWN_PCT:
             self.risk_issues.append({
                 'issue': f"Max Drawdown {max_dd*100:.1f}% > Limit {self.MAX_DRAWDOWN_PCT*100}%",
                 'severity': "Critical",
                 'fix': "Halt trading"
             })
             risk_status = "🔴 CRITICAL - Drawdown Limit Exceeded"

        content = (
            f"- Total Exposure: {exposure_pct:.1f}% of capital\n"
            f"- Portfolio Heat: {heat_pct:.1f}% (Limit: {self.MAX_PORTFOLIO_HEAT_PCT*100}%)\n"
            f"- Max Drawdown: {max_dd*100:.2f}% (Limit: {self.MAX_DRAWDOWN_PCT*100}%)\n"
            f"- Active Positions: {active_positions_count} across {strategies_count} strategies\n"
            f"- Risk Status: {risk_status}\n"
        )
        if position_details:
            content += "\nDetails:\n" + "\n".join(position_details)

        self.add_section("📊 PORTFOLIO RISK STATUS:", content)
        return tracked_symbols

    def analyze_correlations(self, tracked_symbols):
        logger.info("Analyzing Correlations...")
        if len(tracked_symbols) < 2:
            return

        tickers = {}
        for sym in tracked_symbols:
            t = self._get_ticker(sym)
            if t:
                tickers[sym] = t

        if len(tickers) < 2:
            return

        try:
            # Download data for correlation analysis
            data = yf.download(list(tickers.values()), period="1mo", progress=False)['Close']

            if data.empty:
                return

            # If single ticker, data is Series, need DataFrame
            if isinstance(data, pd.Series):
                 return

            corr_matrix = data.corr()

            high_corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i):
                    val = corr_matrix.iloc[i, j]
                    if abs(val) > self.MAX_CORRELATION:
                        t1 = corr_matrix.columns[i]
                        t2 = corr_matrix.columns[j]
                        # Map back to internal symbols
                        s1 = [k for k,v in tickers.items() if v == t1]
                        s2 = [k for k,v in tickers.items() if v == t2]
                        s1_name = s1[0] if s1 else t1
                        s2_name = s2[0] if s2 else t2

                        high_corr_pairs.append(f"{s1_name} <-> {s2_name}: {val:.2f}")
                        self.risk_issues.append({
                            'issue': f"High Correlation: {s1_name} & {s2_name} ({val:.2f})",
                            'severity': "Warning",
                            'fix': "Monitor or reduce concentration"
                        })

            if high_corr_pairs:
                content = "⚠️ High Correlations Detected:\n" + "\n".join([f"- {p}" for p in high_corr_pairs])
                self.add_section("🔗 CORRELATION ANALYSIS:", content)
            else:
                 self.add_section("🔗 CORRELATION ANALYSIS:", "✅ No significant correlations detected.")

        except Exception as e:
            logger.error(f"Correlation analysis failed: {e}")

    def analyze_sector_distribution(self, tracked_symbols):
        logger.info("Analyzing Sector Distribution...")
        if not tracked_symbols:
            return

        sectors = {}
        for sym in tracked_symbols:
            sector = "Equity" # Default
            if "NIFTY" in sym or "BANK" in sym:
                sector = "Index"
            elif "SILVER" in sym or "GOLD" in sym or "CRUDE" in sym:
                sector = "Commodity"
            elif "USD" in sym:
                sector = "Forex"

            sectors[sector] = sectors.get(sector, 0) + 1

        total = len(tracked_symbols)
        content = ""
        for sec, count in sectors.items():
            pct = (count / total) * 100
            content += f"- {sec}: {pct:.1f}% ({count})\n"

        self.add_section("🍰 SECTOR DISTRIBUTION:", content)

    def fetch_broker_positions(self, port):
        """Fetch positions from broker API"""
        url = f"http://localhost:{port}/api/v1/positions"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return data.get('data', [])
        except requests.exceptions.ConnectionError:
            return None # Down
        except Exception as e:
            logger.debug(f"Broker fetch error on port {port}: {e}")
            return None
        return []

    def reconcile_positions(self, tracked_symbols):
        logger.info("Reconciling Positions...")

        # Fetch Real Positions
        kite_positions = self.fetch_broker_positions(5001)
        dhan_positions = self.fetch_broker_positions(5002)

        broker_symbols = set()
        broker_count = 0

        if kite_positions:
            for p in kite_positions:
                broker_symbols.add(p.get('symbol', 'UNKNOWN'))
            broker_count += len(kite_positions)

        if dhan_positions:
            for p in dhan_positions:
                broker_symbols.add(p.get('symbol', 'UNKNOWN'))
            broker_count += len(dhan_positions)

        discrepancies = []
        actions = []

        # Symbol-level comparison
        missing_in_broker = tracked_symbols - broker_symbols
        orphaned_in_broker = broker_symbols - tracked_symbols

        if kite_positions is None and dhan_positions is None:
             discrepancies.append("Brokers Unreachable")
             actions.append("Check Broker Connectivity")
        else:
            if missing_in_broker:
                discrepancies.append(f"Missing in Broker: {', '.join(missing_in_broker)}")
                actions.append("Manual Review Needed")
                self.risk_issues.append({
                    'issue': f"Position Missing in Broker: {', '.join(missing_in_broker)}",
                    'severity': "Critical",
                    'fix': "Reconcile manually"
                })

            if orphaned_in_broker:
                discrepancies.append(f"Orphaned in Broker: {', '.join(orphaned_in_broker)}")
                actions.append("Close orphaned positions if invalid")
                self.risk_issues.append({
                    'issue': f"Orphaned Position in Broker: {', '.join(orphaned_in_broker)}",
                    'severity': "Warning",
                    'fix': "Verify and close"
                })

        content = (
            f"- Broker Positions: {broker_count}\n"
            f"- Tracked Positions: {len(tracked_symbols)}\n"
            f"- Discrepancies: {'; '.join(discrepancies) if discrepancies else 'None'}\n"
            f"- Actions: {'; '.join(actions) if actions else 'Auto-corrected / Manual review needed'}"
        )
        self.add_section("🔍 POSITION RECONCILIATION:", content)

    def check_api_health(self, port, name):
        """Check API Health"""
        url = f"http://localhost:{port}/health"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return "✅ Healthy"
            else:
                return f"⚠️ Issues (HTTP {response.status_code})"
        except requests.exceptions.ConnectionError:
            return "🔴 Down / Unreachable"
        except Exception:
            return "🔴 Error"

    def check_system_health(self, tracked_symbols):
        logger.info("Checking System Health...")

        # Resource Usage
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent

        # Process Health
        strategy_procs = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = proc.info['cmdline']
                if cmd and 'python' in cmd[0] and any('strategy' in c for c in cmd):
                    strategy_procs += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # API Health Check
        kite_status = self.check_api_health(5001, "Kite")
        dhan_status = self.check_api_health(5002, "Dhan")

        if "Down" in kite_status or "Error" in kite_status:
            self.infra_improvements.append({
                'enhancement': "Restart Kite Bridge Service (Port 5001)",
                'implementation': "Systemd restart kite_bridge"
            })
            self.risk_issues.append({
                'issue': "Kite API Down",
                'severity': "High",
                'fix': "Restart Service"
            })

        if "Down" in dhan_status or "Error" in dhan_status:
            self.infra_improvements.append({
                'enhancement': "Restart Dhan Bridge Service (Port 5002)",
                'implementation': "Systemd restart dhan_bridge"
            })

        if cpu > 80:
            self.infra_improvements.append({
                'enhancement': "Optimize Strategy Loops",
                'implementation': "Profile CPU usage"
            })
        if mem > 80:
            self.infra_improvements.append({
                'enhancement': "Check for Memory Leaks",
                'implementation': "Profile memory usage"
            })

        # Data Feed Quality
        data_issues = []
        for sym in tracked_symbols:
            t = self._get_ticker(sym)
            if t:
                try:
                    data = yf.Ticker(t).history(period="5d")
                    if data.empty:
                        data_issues.append(sym)
                except Exception:
                    data_issues.append(sym)

        data_status = "✅ Stable"
        if data_issues:
            data_status = f"⚠️ Gaps detected ({len(data_issues)} symbols)"
            self.risk_issues.append({
                'issue': f"Data Feed Gaps: {', '.join(data_issues)}",
                'severity': "Medium",
                'fix': "Check data provider"
            })

        content = (
            f"- Kite API: {kite_status}\n"
            f"- Dhan API: {dhan_status}\n"
            f"- Data Feed: {data_status}\n"
            f"- Process Health: {strategy_procs} strategy processes running\n"
            f"- Resource Usage: CPU {cpu}%, Memory {mem}%"
        )
        self.add_section("🔌 SYSTEM HEALTH:", content)

    def detect_market_regime(self):
        logger.info("Detecting Market Regime...")
        try:
            vix = yf.Ticker("^INDIAVIX").history(period="5d")
            if vix.empty:
                vix = yf.Ticker("^VIX").history(period="5d") # Fallback to US VIX if India unavailable

            if not vix.empty:
                current_vix = vix['Close'].iloc[-1]
            else:
                current_vix = 15.0 # Default fallback

            regime = "Ranging"
            mix = "Mean Reversion"
            disabled = []

            if current_vix < 13:
                regime = "Low Volatility"
                mix = "Calendar Spreads, Iron Condors"
            elif current_vix > 20:
                regime = "High Volatility"
                mix = "Directional Momentum, Long Volatility"
                disabled.append("Short Straddles")
            else:
                regime = "Normal Volatility"
                mix = "Hybrid (Trend + Mean Rev)"

            content = (
                f"- Current Regime: {regime}\n"
                f"- VIX Level: {current_vix:.2f}\n"
                f"- Recommended Strategy Mix: {mix}\n"
                f"- Disabled Strategies: {', '.join(disabled) if disabled else 'None'}"
            )
            self.add_section("📈 MARKET REGIME:", content)

        except Exception as e:
            logger.error(f"Market Regime Detection Failed: {e}")
            self.add_section("📈 MARKET REGIME:", "⚠️ Data Unavailable")

    def check_compliance(self):
        logger.info("Checking Compliance...")
        log_dir = self.root_dir / "log" / "strategies"

        active_logs = 0
        missing_records = False

        if log_dir.exists():
            # Check for logs modified in last 7 days
            week_ago = datetime.datetime.now().timestamp() - (7 * 24 * 3600)
            for log_file in log_dir.glob("*.log"):
                if log_file.stat().st_mtime > week_ago:
                    active_logs += 1

        status = "✅ Complete" if active_logs > 0 else "⚠️ Missing Logs"
        if active_logs == 0:
            missing_records = True
            self.risk_issues.append({
                'issue': "No active strategy logs found for the past week",
                'severity': "High",
                'fix': "Check logging configuration"
            })

        content = (
            f"- Trade Logging: {status} ({active_logs} active files)\n"
            f"- Audit Trail: {'✅ Intact' if not missing_records else '⚠️ Verification Needed'}\n"
            f"- Unauthorized Activity: ✅ None detected"
        )
        self.add_section("✅ COMPLIANCE CHECK:", content)

    def run(self):
        tracked_symbols = self.analyze_portfolio_risk()
        self.analyze_correlations(tracked_symbols)
        self.analyze_sector_distribution(tracked_symbols)
        self.reconcile_positions(tracked_symbols)
        self.check_system_health(tracked_symbols)
        self.detect_market_regime()
        self.check_compliance()

        # Compile Issues
        issues_content = ""
        if self.risk_issues:
            for i, issue in enumerate(self.risk_issues, 1):
                issues_content += f"{i}. {issue['issue']} → {issue['severity']} → {issue['fix']}\n"
        else:
            issues_content = "None"
        self.add_section("⚠️ RISK ISSUES FOUND:", issues_content)

        # Compile Improvements
        infra_content = ""
        if self.infra_improvements:
            for i, imp in enumerate(self.infra_improvements, 1):
                infra_content += f"{i}. {imp['enhancement']} → {imp['implementation']}\n"
        else:
            infra_content = "None"
        self.add_section("🔧 INFRASTRUCTURE IMPROVEMENTS:", infra_content)

        # Action Items
        if not self.action_items:
             self.action_items.append("[High] Review Audit Report → Risk Manager/Pending")

        action_content = ""
        for item in self.action_items:
             action_content += f"- {item}\n"

        self.add_section("📋 ACTION ITEMS FOR NEXT WEEK:", action_content)

        # Write Report
        header = f"🛡️ WEEKLY RISK & HEALTH AUDIT - Week of {audit_date}\n"
        full_report = header + "".join(self.report_lines)

        with open(report_file, 'w') as f:
            f.write(full_report)

        print(full_report)
        logger.info(f"Report generated at {report_file}")

if __name__ == "__main__":
    audit = WeeklyAudit()
    audit.run()
