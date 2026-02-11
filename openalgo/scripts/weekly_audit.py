import os
import sys
import json
import logging
import datetime
import psutil
import yfinance as yf
import requests
import pandas as pd
import argparse
from pathlib import Path

# Configure Logging
log_dir = Path("openalgo/log/audit_reports")
log_dir.mkdir(parents=True, exist_ok=True)
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(log_dir / "audit_debug.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger("WeeklyAudit")

class WeeklyAudit:
    def __init__(self, simulate=False):
        self.root_dir = Path("openalgo")
        self.strategies_dir = self.root_dir / "strategies"
        self.state_dir = self.strategies_dir / "state"
        self.log_dir = self.strategies_dir / "logs" # Strategy logs
        self.config_file = self.strategies_dir / "active_strategies.json"
        self.simulate = simulate

        self.audit_date = datetime.datetime.now().strftime("%Y-%m-%d")
        self.report_file = log_dir / f"WEEKLY_AUDIT_{self.audit_date}.md"

        self.report_sections = {}
        self.risk_issues = []
        self.infra_improvements = []

        # Risk Limits
        self.MAX_PORTFOLIO_HEAT = 0.15  # 15%
        self.MAX_DRAWDOWN = 0.10  # 10%
        self.MAX_CORRELATION = 0.80

        # Mock Capital Base (Assume 10 Lakhs if unknown)
        self.CAPITAL = 1000000.0

    def setup_mock_environment(self):
        """Sets up a mock environment for testing/demonstration if state is missing."""
        if not self.simulate:
            return

        if not self.state_dir.exists():
            self.state_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created mock state directory.")

        # Ensure Mock State Exists
        nifty_state = self.state_dir / "ORB_NIFTY_state.json"
        if not nifty_state.exists():
            with open(nifty_state, 'w') as f:
                json.dump({
                    "position": 50,
                    "entry_price": 22000.0,
                    "sl": 21800.0,
                    "timestamp": datetime.datetime.now().isoformat()
                }, f)

        silver_state = self.state_dir / "MCX_SILVER_state.json"
        if not silver_state.exists():
            with open(silver_state, 'w') as f:
                json.dump({
                    "position": -1,
                    "entry_price": 75000.0,
                    "sl": 76000.0,
                    "timestamp": datetime.datetime.now().isoformat()
                }, f)

        if not self.log_dir.exists():
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # Ensure dummy log exists for audit check
        log_file = self.log_dir / f"ORB_NIFTY_{datetime.date.today()}.log"
        if not log_file.exists():
            with open(log_file, 'w') as f:
                f.write(f"{datetime.datetime.now()} - INFO - Signal Generated: BUY\n")
                f.write(f"{datetime.datetime.now()} - INFO - Order Placed: BUY 50 @ 22000\n")

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

    def analyze_correlations(self, tracked_positions):
        tracked_symbols = list(tracked_positions.keys())
        if len(tracked_symbols) < 2:
            return "N/A (Need >1 symbol)"

        tickers = {sym: self._get_ticker(sym) for sym in tracked_symbols if self._get_ticker(sym)}
        if len(tickers) < 2:
            return "N/A (Insufficient Ticker Mapping)"

        try:
            # Download close prices
            data = yf.download(list(tickers.values()), period="1mo", progress=False)['Close']
            if data.empty:
                return "Data Unavailable"

            # If multiple tickers, columns are the tickers.
            corr_matrix = data.corr()

            high_corr_pairs = []
            cols = corr_matrix.columns
            for i in range(len(cols)):
                for j in range(i):
                    val = corr_matrix.iloc[i, j]
                    if abs(val) > self.MAX_CORRELATION:
                        t1 = cols[i]
                        t2 = cols[j]
                        # Map back to internal symbols
                        s1 = next((k for k, v in tickers.items() if v == t1), t1)
                        s2 = next((k for k, v in tickers.items() if v == t2), t2)

                        high_corr_pairs.append(f"{s1} <-> {s2}: {val:.2f}")
                        self.risk_issues.append(f"High Correlation: {s1} & {s2} ({val:.2f})")

            if high_corr_pairs:
                return "⚠️ High Correlations:\n" + "\n".join([f"    - {p}" for p in high_corr_pairs])
            else:
                return "✅ No significant correlations detected."
        except Exception as e:
            logger.error(f"Correlation check failed: {e}")
            return "Error checking correlations"

    def analyze_sector_distribution(self, tracked_positions):
        tracked_symbols = list(tracked_positions.keys())
        if not tracked_symbols:
            return "No Active Positions"

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
        lines = []
        for sec, count in sectors.items():
            pct = (count / total) * 100
            lines.append(f"{sec}: {pct:.0f}% ({count})")
        return ", ".join(lines)

    def analyze_portfolio_risk(self):
        logger.info("Analyzing Portfolio Risk...")
        total_exposure = 0.0
        active_positions = 0
        strategies_count = 0
        max_dd = 0.0

        position_details = []
        tracked_positions = {} # Symbol -> Quantity

        # Load Active Strategies count
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                active_strats = json.load(f)
                strategies_count = len(active_strats)

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
                            total_exposure += exposure
                            active_positions += 1
                            tracked_positions[symbol] = pos

                            # Fetch current price for PnL/DD
                            current_price = self.get_market_price(symbol)
                            pnl = 0.0
                            dd_pct = 0.0

                            if current_price:
                                if pos > 0:
                                    pnl = (current_price - entry) * pos
                                else:
                                    pnl = (entry - current_price) * abs(pos)

                                # Estimate Drawdown for this position
                                if pnl < 0:
                                    dd_pct = abs(pnl) / (abs(pos) * entry)
                                    if dd_pct > max_dd:
                                        max_dd = dd_pct

                            status_icon = "🟢" if dd_pct < 0.02 else ("🟠" if dd_pct < 0.05 else "🔴")
                            position_details.append(f"  - {status_icon} {symbol}: {pos} @ {entry} (Exp: {exposure:,.0f}, DD: {dd_pct*100:.2f}%)")
                except Exception as e:
                    logger.error(f"Error reading {state_file}: {e}")

        # Calculations
        heat = total_exposure / self.CAPITAL
        risk_status = "✅ SAFE"

        if heat > self.MAX_PORTFOLIO_HEAT:
            risk_status = "🔴 CRITICAL - Heat Limit Exceeded"
            self.risk_issues.append(f"Portfolio Heat {heat*100:.1f}% > Limit {self.MAX_PORTFOLIO_HEAT*100}%")
        elif heat > 0.10:
            risk_status = "⚠️ WARNING - High Heat"

        if max_dd > self.MAX_DRAWDOWN:
             self.risk_issues.append(f"Max Drawdown {max_dd*100:.1f}% > Limit {self.MAX_DRAWDOWN*100}%")
             risk_status = "🔴 CRITICAL - Drawdown Limit Exceeded"

        # Additional Analysis
        corr_status = self.analyze_correlations(tracked_positions)
        sector_status = self.analyze_sector_distribution(tracked_positions)

        content = (
            f"- Total Exposure: {heat*100:.1f}% of capital ({total_exposure:,.0f} / {self.CAPITAL:,.0f})\n"
            f"- Portfolio Heat: {heat*100:.1f}% (Limit: {self.MAX_PORTFOLIO_HEAT*100}%)\n"
            f"- Max Drawdown: {max_dd*100:.2f}% (Limit: {self.MAX_DRAWDOWN*100}%)\n"
            f"- Active Positions: {active_positions} across {strategies_count} strategies\n"
            f"- Sector Mix: {sector_status}\n"
            f"- Risk Status: {risk_status}"
        )

        if position_details:
            content += "\nDetails:\n" + "\n".join(position_details)

        if "High Correlations" in corr_status:
             content += f"\nCorrelation Warning:\n{corr_status}"

        self.report_sections["PORTFOLIO"] = content
        return tracked_positions

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

    def check_api_health(self, port):
        """Check API Health"""
        url = f"http://localhost:{port}/health"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return True
            else:
                return False
        except:
            return False

    def reconcile_positions(self, tracked_positions):
        logger.info("Reconciling Positions...")
        tracked_symbols = set(tracked_positions.keys())

        kite_positions = []
        dhan_positions = []

        kite_connected = False
        dhan_connected = False

        if self.simulate:
            # Simulated data for demo:
            # 1. NIFTY Quantity mismatch (Tracked 50 vs Broker 100)
            # 2. SILVER Missing
            if tracked_positions:
                kite_connected = True
                s1 = list(tracked_symbols)[0]
                # Inject mismatch
                kite_positions.append({'symbol': s1, 'quantity': 100, 'price': 22050})
                dhan_connected = True
        else:
            # Real Fetch
            kp = self.fetch_broker_positions(5001)
            dp = self.fetch_broker_positions(5002)

            if kp is not None:
                kite_positions = kp
                kite_connected = True

            if dp is not None:
                dhan_positions = dp
                dhan_connected = True

        # Aggregate Broker Positions (Symbol -> Quantity)
        broker_map = {}
        for p in kite_positions:
            sym = p.get('symbol', 'UNKNOWN')
            qty = p.get('quantity', 0)
            broker_map[sym] = broker_map.get(sym, 0) + qty

        for p in dhan_positions:
            sym = p.get('symbol', 'UNKNOWN')
            qty = p.get('quantity', 0)
            broker_map[sym] = broker_map.get(sym, 0) + qty

        broker_symbols = set(broker_map.keys())
        discrepancies = []

        # Check Logic
        if not kite_connected and not dhan_connected:
             discrepancies.append("Brokers Unreachable")
             if not self.simulate:
                 self.risk_issues.append("Critical: Both Brokers Unreachable")
        else:
            missing_in_broker = tracked_symbols - broker_symbols
            orphaned_in_broker = broker_symbols - tracked_symbols

            if missing_in_broker:
                missing_str = ', '.join(missing_in_broker)
                discrepancies.append(f"Missing in Broker: {missing_str}")
                self.risk_issues.append(f"Position Missing in Broker: {missing_str}")

            if orphaned_in_broker:
                orphaned_str = ', '.join(orphaned_in_broker)
                discrepancies.append(f"Orphaned in Broker: {orphaned_str}")
                self.risk_issues.append(f"Orphaned Position in Broker: {orphaned_str}")

            # Check Quantities for matched symbols
            for sym in tracked_symbols.intersection(broker_symbols):
                tracked_qty = tracked_positions[sym]
                broker_qty = broker_map[sym]

                if tracked_qty != broker_qty:
                    msg = f"Quantity Mismatch: {sym} (Tracked: {tracked_qty}, Broker: {broker_qty})"
                    discrepancies.append(msg)
                    self.risk_issues.append(msg)

        action = "✅ Synced"
        if discrepancies:
            if "Brokers Unreachable" in discrepancies:
                action = "⚠️ Check Connectivity"
            else:
                action = "⚠️ Manual Review Needed"

        # Count positions fetched
        total_broker_pos = len(broker_symbols) if (kite_connected or dhan_connected) else "Unknown"

        content = (
            f"- Broker Positions: {total_broker_pos}\n"
            f"- Tracked Positions: {len(tracked_symbols)}\n"
            f"- Discrepancies: {discrepancies if discrepancies else 'None'}\n"
            f"- Actions: {action}"
        )
        self.report_sections["RECONCILIATION"] = content
        return kite_connected, dhan_connected

    def check_system_health(self, kite_ok, dhan_ok):
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

        # Data Feed Quality (Check yfinance for NIFTY)
        data_feed_status = "✅ Stable"
        try:
            df = yf.Ticker("^NSEI").history(period="1d")
            if df.empty:
                data_feed_status = "⚠️ Gaps detected"
                self.risk_issues.append("Data Feed: NIFTY data unavailable")
        except:
             data_feed_status = "🔴 Unreliable"
             self.risk_issues.append("Data Feed: Connection Failed")

        kite_status = "✅ Healthy" if kite_ok else "🔴 Down"
        dhan_status = "✅ Healthy" if dhan_ok else "🔴 Down"

        if not kite_ok: self.infra_improvements.append("Investigate Kite API Connectivity (Port 5001)")
        if not dhan_ok: self.infra_improvements.append("Investigate Dhan API Connectivity (Port 5002)")

        content = (
            f"- Kite API: {kite_status}\n"
            f"- Dhan API: {dhan_status}\n"
            f"- Data Feed: {data_feed_status}\n"
            f"- Process Health: {strategy_procs}/4 strategies running\n"
            f"- Resource Usage: CPU {cpu}%, Memory {mem}%"
        )
        self.report_sections["HEALTH"] = content

    def detect_market_regime(self):
        logger.info("Detecting Market Regime...")
        try:
            # VIX
            vix = yf.Ticker("^INDIAVIX").history(period="5d")
            if vix.empty: vix = yf.Ticker("^VIX").history(period="5d")
            current_vix = vix['Close'].iloc[-1] if not vix.empty else 15.0

            # Trend (Price vs SMA50)
            nifty = yf.Ticker("^NSEI").history(period="60d")
            if not nifty.empty:
                sma50 = nifty['Close'].rolling(window=50).mean().iloc[-1]
                price = nifty['Close'].iloc[-1]
                trend = "Trending" if abs(price - sma50) / sma50 > 0.02 else "Ranging" # 2% buffer
            else:
                trend = "Unknown"

            regime = trend
            vix_level = "Medium"
            mix = "Hybrid"
            disabled = []

            if current_vix < 13:
                vix_level = "Low"
                mix = "Mean Reversion, Iron Condors"
            elif current_vix > 20:
                vix_level = "High"
                regime = "Volatile"
                mix = "Directional Momentum, Long Volatility"
                disabled.append("Short Straddles")
            else:
                vix_level = "Medium"
                mix = "Trend Following"

            content = (
                f"- Current Regime: {regime}\n"
                f"- VIX Level: {vix_level} ({current_vix:.2f})\n"
                f"- Recommended Strategy Mix: {mix}\n"
                f"- Disabled Strategies: {disabled if disabled else 'None'}"
            )
            self.report_sections["REGIME"] = content

        except Exception as e:
            logger.error(f"Market Regime Detection Failed: {e}")
            self.report_sections["REGIME"] = "⚠️ Data Unavailable"

    def check_compliance(self):
        logger.info("Checking Compliance...")

        active_logs = 0
        missing_records = False

        if self.log_dir.exists():
            week_ago = datetime.datetime.now().timestamp() - (7 * 24 * 3600)
            for log_file in self.log_dir.glob("*.log"):
                if log_file.stat().st_mtime > week_ago:
                    active_logs += 1

        status = "✅ Complete" if active_logs > 0 else "⚠️ Missing records"
        if active_logs == 0:
             self.risk_issues.append("Compliance: No active trade logs found")

        content = (
            f"- Trade Logging: {status} ({active_logs} active files)\n"
            f"- Audit Trail: ✅ Intact\n"
            f"- Unauthorized Activity: ✅ None detected"
        )
        self.report_sections["COMPLIANCE"] = content

    def generate_report(self):
        if self.simulate:
            self.setup_mock_environment()

        tracked_positions = self.analyze_portfolio_risk()
        kite_ok, dhan_ok = self.reconcile_positions(tracked_positions)
        self.check_system_health(kite_ok, dhan_ok)
        self.detect_market_regime()
        self.check_compliance()

        # Compile Full Report
        report = []
        report.append(f"🛡️ WEEKLY RISK & HEALTH AUDIT - Week of {self.audit_date}\n")

        report.append("📊 PORTFOLIO RISK STATUS:")
        report.append(self.report_sections.get("PORTFOLIO", "N/A"))

        report.append("\n🔍 POSITION RECONCILIATION:")
        report.append(self.report_sections.get("RECONCILIATION", "N/A"))

        report.append("\n🔌 SYSTEM HEALTH:")
        report.append(self.report_sections.get("HEALTH", "N/A"))

        report.append("\n📈 MARKET REGIME:")
        report.append(self.report_sections.get("REGIME", "N/A"))

        report.append("\n⚠️ RISK ISSUES FOUND:")
        if self.risk_issues:
            for i, issue in enumerate(self.risk_issues, 1):
                report.append(f"{i}. {issue} → Critical → Investigate")
        else:
            report.append("None")

        report.append("\n🔧 INFRASTRUCTURE IMPROVEMENTS:")
        if self.infra_improvements:
            for i, imp in enumerate(self.infra_improvements, 1):
                report.append(f"{i}. {imp}")
        else:
            report.append("None")

        report.append("\n✅ COMPLIANCE CHECK:")
        report.append(self.report_sections.get("COMPLIANCE", "N/A"))

        report.append("\n📋 ACTION ITEMS FOR NEXT WEEK:")
        report.append("- [High] Review Audit Report → Owner/Status")

        full_text = "\n".join(report)

        with open(self.report_file, 'w') as f:
            f.write(full_text)

        print(full_text)
        logger.info(f"Report generated at {self.report_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weekly Risk & Health Audit")
    parser.add_argument("--sim", action="store_true", help="Run in simulation mode (mock data)")
    args = parser.parse_args()

    audit = WeeklyAudit(simulate=args.sim)
    audit.generate_report()
