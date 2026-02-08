import sys
import os
import json
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import importlib.util

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LeaderboardGen")

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.append(repo_root)

# Import SimpleBacktestEngine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

class MockAPIClient:
    def __init__(self, api_key=None, host=None):
        self.api_key = api_key
        self.host = host
        self.symbol_map = {
            "NIFTY": "^NSEI",
            "NIFTY 50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "NIFTY BANK": "^NSEBANK",
            "SILVERMIC": "SI=F",
            "SILVER": "SI=F",
            "GOLDM": "GC=F",
            "CRUDEOIL": "CL=F",
            "INDIA VIX": "^INDIAVIX"
        }

    def history(self, symbol, exchange="NSE", interval="15m", start_date=None, end_date=None, **kwargs):
        yf_symbol = self.symbol_map.get(symbol, symbol)

        # YF interval format
        # YF only supports 7d of 1m data, 60d of 2m/5m/15m/30m/90m.
        # If interval is "day" or "1d", YF supports max available.

        yf_interval = interval
        if interval == "day": yf_interval = "1d"

        # Convert dates to YYYY-MM-DD
        try:
            # If start_date is too old for 15m, YF will error or return empty.
            # Max 60 days for 15m.
            # Max 730 days for 60m/1h.

            days_limit = 60
            if interval in ["60m", "1h"]:
                days_limit = 730
            elif interval in ["1d", "day"]:
                days_limit = 36500 # Unlimited effectively

            if interval.endswith("m") or interval.endswith("h"):
                # Check if start_date is within limit days
                # But relative to Real World (server time), not necessarily datetime.now() if mocked?
                # Actually YF checks against real world.
                # Since datetime.now() here is 2026, calculating limit_date based on it is WRONG for YF checks
                # if we want to fetch 2024 data.
                # However, if we assume we just pass dates to YF and let it fail/succeed.
                # But I added a check `if start_dt < limit_date`. I should REMOVE/RELAX this check.
                # Or base it on 2025 (Real World).

                # Let's just remove the check and trust YF or just warn.
                pass

            logger.info(f"Downloading {yf_symbol} ({interval}) from {start_date} to {end_date}")
            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=yf_interval, progress=False, multi_level_index=False)

            if df.empty:
                logger.warning(f"No data for {yf_symbol}")
                return pd.DataFrame()

            # Rename columns to lowercase
            df.columns = [c.lower() for c in df.columns]

            # Ensure index name is datetime or timestamp
            if df.index.name == 'Date':
                df.index.name = 'datetime'

            # If TZ aware, make naive for simplicity in backtest engine comparisons if needed
            # But usually it's fine.
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)

            # Fix 0 volume for Indexes (YFinance issue)
            if 'volume' in df.columns and (df['volume'] == 0).all():
                logger.warning(f"Volume is 0 for {symbol}. Mocking volume.")
                import numpy as np
                df['volume'] = np.random.randint(100000, 200000, size=len(df))

            logger.info(f"First 2 rows of {symbol}: \n{df.head(2)}")
            return df

        except Exception as e:
            logger.error(f"YF Download Error for {symbol}: {e}")
            return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE"):
        # Mock quote
        return {'ltp': 0.0, 'close': 0.0}

    def placesmartorder(self, *args, **kwargs):
        # Mock order placement
        return {"status": "success", "order_id": "mock_123"}

STRATEGIES = [
    {
        "name": "SuperTrend_VWAP",
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "MCX_Momentum",
        "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
        "symbol": "SILVERMIC",
        "exchange": "MCX"
    },
    {
        "name": "AI_Hybrid",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    },
    {
        "name": "Gap_Fade",
        "file": "openalgo/strategies/scripts/gap_fade_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX"
    }
]

def load_strategy_module(filepath):
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        full_path = os.path.join(repo_root, filepath)
        spec = importlib.util.spec_from_file_location(module_name, full_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def run_backtests():
    # Initialize Engine with Mock Client
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    engine.client = MockAPIClient() # Inject Mock Client

    # Use fixed date range valid for YFinance (Real World Data)
    # Assuming real world is early 2025, we use late 2024/early 2025
    start_date = "2024-12-01"
    end_date = "2025-01-31"

    results = []

    for strat_config in STRATEGIES:
        logger.info(f"--- Backtesting {strat_config['name']} ---")
        module = load_strategy_module(strat_config['file'])

        if not module or not hasattr(module, 'generate_signal'):
            logger.warning(f"Skipping {strat_config['name']} (No generate_signal)")
            continue

        try:
            res = engine.run_backtest(
                strategy_module=module,
                symbol=strat_config['symbol'],
                exchange=strat_config['exchange'],
                start_date=start_date,
                end_date=end_date,
                interval="60m"
            )

            if 'error' in res:
                logger.error(f"Backtest failed for {strat_config['name']}: {res['error']}")
                continue

            metrics = res.get('metrics', {})
            results.append({
                "strategy": strat_config['name'],
                "total_return": metrics.get('total_return_pct', 0),
                "sharpe": metrics.get('sharpe_ratio', 0),
                "drawdown": metrics.get('max_drawdown_pct', 0),
                "win_rate": metrics.get('win_rate', 0),
                "trades": res.get('total_trades', 0),
                "profit_factor": metrics.get('profit_factor', 0)
            })

        except Exception as e:
            logger.error(f"Error executing backtest for {strat_config['name']}: {e}", exc_info=True)

    # Sort
    results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

    # Save
    log_dir = os.path.join(repo_root, "openalgo", "log")
    os.makedirs(log_dir, exist_ok=True)

    with open(os.path.join(log_dir, "leaderboard.json"), "w") as f:
        json.dump(results, f, indent=4)

    # Markdown
    md = "# Strategy Leaderboard (Baseline)\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n"
    md += f"**Period:** {start_date} to {end_date} (60 Days)\n\n"
    md += "| Rank | Strategy | Sharpe | Return % | Max DD % | Win Rate % | Trades | PF |\n"
    md += "|---|---|---|---|---|---|---|---|\n"

    for i, r in enumerate(results):
        md += f"| {i+1} | {r['strategy']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['trades']} | {r['profit_factor']:.2f} |\n"

    with open(os.path.join(log_dir, "LEADERBOARD.md"), "w") as f:
        f.write(md)

    logger.info(f"Leaderboard generated at {os.path.join(log_dir, 'LEADERBOARD.md')}")

if __name__ == "__main__":
    run_backtests()
