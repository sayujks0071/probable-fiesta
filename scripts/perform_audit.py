#!/usr/bin/env python3
import os
import sys
import json
import logging
import psutil
import requests
import datetime
from pathlib import Path

# Add openalgo to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure basic logging for the script itself
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Audit")

def check_portfolio_risk():
    """Analyze active positions and risk."""
    state_dir = Path("openalgo/strategies/state")
    if not state_dir.exists():
        return {
            "status": "CRITICAL",
            "message": "State directory missing",
            "positions": [],
            "exposure": 0.0,
            "heat": 0.0,
            "strategies": 0
        }

    positions = []
    total_exposure = 0.0
    active_strategies = set()

    try:
        for file in state_dir.glob("*.json"):
            with open(file, 'r') as f:
                data = json.load(f)
                active_strategies.add(file.stem.replace('_state', ''))
                pos_map = data.get('positions', {})
                for symbol, pos in pos_map.items():
                    qty = pos.get('qty', 0)
                    entry = pos.get('entry_price', 0.0)
                    exposure = abs(qty * entry)
                    total_exposure += exposure
                    positions.append({
                        "symbol": symbol,
                        "qty": qty,
                        "entry": entry,
                        "exposure": exposure,
                        "strategy": file.stem
                    })
    except Exception as e:
        return {"status": "ERROR", "message": str(e), "positions": [], "exposure": 0.0}

    # Mock capital for % calculation (assume 10L)
    capital = 1000000.0
    heat = (total_exposure / capital) * 100

    status = "SAFE"
    if heat > 15:
        status = "CRITICAL"
    elif heat > 10:
        status = "WARNING"

    return {
        "status": status,
        "message": "OK" if status == "SAFE" else f"High Exposure: {heat:.1f}%",
        "positions": positions,
        "exposure": total_exposure,
        "heat": heat,
        "strategies": len(active_strategies)
    }

def reconcile_positions(internal_positions):
    """Compare internal state with broker (mocked)."""
    # In a real scenario, we'd fetch from APIs
    broker_positions = [] # Mocked empty for now as we can't reach broker

    discrepancies = []
    # Simplified reconciliation logic
    internal_map = {p['symbol']: p['qty'] for p in internal_positions}
    broker_map = {p['symbol']: p['qty'] for p in broker_positions}

    for sym, qty in internal_map.items():
        if sym not in broker_map:
            discrepancies.append(f"Missing in Broker: {sym} ({qty})")
        elif broker_map[sym] != qty:
            discrepancies.append(f"Qty Mismatch: {sym} (Internal: {qty}, Broker: {broker_map[sym]})")

    for sym, qty in broker_map.items():
        if sym not in internal_map:
            discrepancies.append(f"Orphaned in Broker: {sym} ({qty})")

    return {
        "broker_count": len(broker_positions),
        "internal_count": len(internal_positions),
        "discrepancies": discrepancies,
        "action": "Manual review needed" if discrepancies else "None"
    }

def check_system_health():
    """Check APIs and Processes."""
    # Check APIs
    kite_status = "🔴 Down"
    dhan_status = "🔴 Down"

    try:
        requests.get("http://localhost:5001/health", timeout=1)
        kite_status = "✅ Healthy"
    except:
        pass

    try:
        requests.get("http://localhost:5002/health", timeout=1)
        dhan_status = "✅ Healthy"
    except:
        pass

    # Check Processes
    strategies_running = 0
    cpu_usage = psutil.cpu_percent(interval=0.1)
    mem_usage = psutil.virtual_memory().percent

    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmd = proc.info['cmdline']
            if cmd and 'python' in cmd[0] and any('strategy' in c for c in cmd):
                strategies_running += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return {
        "kite": kite_status,
        "dhan": dhan_status,
        "strategies_running": strategies_running,
        "cpu": cpu_usage,
        "memory": mem_usage
    }

def analyze_market_regime():
    """Analyze market utilizing yfinance."""
    try:
        import yfinance as yf
        # Suppress yfinance output
        logging.getLogger('yfinance').setLevel(logging.CRITICAL)

        # Check VIX
        vix = yf.Ticker("^INDIAVIX").history(period="5d")
        if vix.empty:
            return {"regime": "Unknown", "vix": "Unknown", "status": "🔴 Unreliable"}

        current_vix = vix['Close'].iloc[-1]
        vix_level = "Low" if current_vix < 15 else "High" if current_vix > 20 else "Medium"

        # Check Nifty Trend (Simple MA)
        nifty = yf.Ticker("^NSEI").history(period="20d")
        if nifty.empty:
            trend = "Unknown"
        else:
            ma20 = nifty['Close'].mean()
            current_price = nifty['Close'].iloc[-1]
            trend = "Trending" if abs(current_price - ma20) / ma20 > 0.02 else "Ranging"

        return {
            "regime": trend,
            "vix": vix_level,
            "status": "✅ Stable"
        }
    except Exception:
        return {"regime": "Unknown", "vix": "Unknown", "status": "🔴 Unreliable"}

def check_compliance():
    """Verify logs."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {
            "status": "CRITICAL",
            "message": "logs directory missing",
            "audit_trail": "🔴 Missing"
        }

    # Check for recent logs
    recent_logs = False
    for file in log_dir.glob("*.log"):
        if (datetime.datetime.now().timestamp() - file.stat().st_mtime) < 86400:
            recent_logs = True
            break

    return {
        "status": "✅ Complete" if recent_logs else "⚠️ Missing recent logs",
        "audit_trail": "✅ Intact" if log_dir.exists() else "🔴 Missing"
    }

def main():
    print(f"🛡️ WEEKLY RISK & HEALTH AUDIT - Week of {datetime.date.today()}")
    print()

    # 1. Portfolio Risk
    risk = check_portfolio_risk()
    print("📊 PORTFOLIO RISK STATUS:")
    print(f"- Total Exposure: {risk['exposure']:.2f}") # Absolute value
    print(f"- Portfolio Heat: {risk['heat']:.2f}% (Limit: 15%)")
    print(f"- Active Positions: {len(risk['positions'])} across {risk['strategies']} strategies")
    print(f"- Risk Status: {('✅ ' if risk['status'] == 'SAFE' else '⚠️ ' if risk['status'] == 'WARNING' else '🔴 ') + risk['status']}")
    print()

    # 2. Position Reconciliation
    rec = reconcile_positions(risk['positions'])
    print("🔍 POSITION RECONCILIATION:")
    print(f"- Broker Positions: {rec['broker_count']}")
    print(f"- Tracked Positions: {rec['internal_count']}")
    if rec['discrepancies']:
        print("- Discrepancies:")
        for d in rec['discrepancies']:
            print(f"  - {d}")
    else:
        print("- Discrepancies: None")
    print(f"- Actions: {rec['action']}")
    print()

    # 3. System Health
    health = check_system_health()
    market = analyze_market_regime()
    print("🔌 SYSTEM HEALTH:")
    print(f"- Kite API: {health['kite']}")
    print(f"- Dhan API: {health['dhan']}")
    print(f"- Data Feed: {market['status']}")
    print(f"- Process Health: {health['strategies_running']} strategies running")
    print(f"- Resource Usage: CPU {health['cpu']}%, Memory {health['memory']}%")
    print()

    # 4. Market Regime
    print("📈 MARKET REGIME:")
    print(f"- Current Regime: {market['regime']}")
    print(f"- VIX Level: {market['vix']}")
    print()

    # 5. Risks Found
    print("⚠️ RISK ISSUES FOUND:")
    issues = []
    if risk['status'] != 'SAFE':
        msg = f"Portfolio Heat High ({risk['heat']:.1f}%) → Critical → Reduce positions"
        if risk['message'] == "State directory missing":
            msg = "State directory missing → Critical → Create directory"
        issues.append(msg)
    if health['kite'] == "🔴 Down":
        issues.append("Kite API Down → Critical → Check connection")
    if health['dhan'] == "🔴 Down":
        issues.append("Dhan API Down → Critical → Check connection")
    if market['status'] == "🔴 Unreliable":
        issues.append("Data Feed Unreliable → Critical → Check internet/proxy")

    # Check directories
    if not Path("openalgo/strategies/state").exists():
        issues.append("State directory missing → Critical → Create directory")
    if not Path("logs").exists():
        issues.append("Logs directory missing → Critical → Create directory")

    if not issues:
        print("None")
    else:
        for i, issue in enumerate(issues, 1):
            print(f"{i}. {issue}")
    print()

    # 6. Infrastructure Improvements
    print("🔧 INFRASTRUCTURE IMPROVEMENTS:")
    print("1. Add automated directory creation on startup")
    print("2. Implement real broker API health check endpoints")
    print()

    # 7. Compliance
    comp = check_compliance()
    print("✅ COMPLIANCE CHECK:")
    print(f"- Trade Logging: {comp['status']}")
    print(f"- Audit Trail: {comp['audit_trail']}")
    print()

    # 8. Action Items
    print("📋 ACTION ITEMS FOR NEXT WEEK:")
    if issues:
         print(f"- [High] Fix {len(issues)} critical issues → Admin/Open")
    else:
         print("- [Medium] Review strategy performance → Analyst/Open")

if __name__ == "__main__":
    main()
