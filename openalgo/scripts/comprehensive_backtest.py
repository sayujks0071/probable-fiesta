#!/usr/bin/env python3
"""
Comprehensive Backtest Leaderboard Script
-----------------------------------------
Scans all strategy files in openalgo/strategies/scripts/
Runs backtests using yfinance data (via MockAPIClient).
Generates a comprehensive leaderboard.
"""

import os
import sys
import json
import logging
import importlib.util
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ComprehensiveBacktest")

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Import SimpleBacktestEngine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Fallback path logic
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine


class MockAPIClient:
    """
    Mock API Client that uses yfinance to fetch historical data.
    """
    def __init__(self, api_key=None, host=None):
        self.api_key = api_key
        self.host = host

    def history(self, symbol, exchange="NSE", interval="15m", start_date=None, end_date=None):
        """Fetch historical data from yfinance."""
        yf_symbol = self._map_symbol(symbol, exchange)
        yf_interval = self._map_interval(interval)

        try:
            # yfinance expects start and end as YYYY-MM-DD strings
            # If end_date is today, yfinance might need tomorrow to include today's data fully?
            # Or just use standard behavior.

            logger.info(f"Fetching {yf_symbol} ({interval}) from {start_date} to {end_date}")
            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=yf_interval, progress=False, auto_adjust=True)

            if df.empty:
                logger.warning(f"No data for {yf_symbol}")
                return pd.DataFrame()

            # Normalize columns
            # yfinance 0.2+ returns MultiIndex columns (Price, Ticker) even for single ticker sometimes
            if isinstance(df.columns, pd.MultiIndex):
                # Drop the ticker level if it exists
                if df.columns.nlevels > 1:
                    df.columns = df.columns.droplevel(1)

            # Reset index to get Date/Datetime as column if needed, or keep as index.
            # SimpleBacktestEngine expects index to be datetime or 'datetime' column.

            df.columns = [c.lower() for c in df.columns]

            # Ensure 'close' exists
            if 'close' not in df.columns and 'adj close' in df.columns:
                df['close'] = df['adj close']

            # Ensure 'volume' exists
            if 'volume' not in df.columns:
                df['volume'] = 0

            return df

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def _map_symbol(self, symbol, exchange):
        """Map internal symbol to yfinance symbol."""
        s = symbol.upper().replace(' ', '')

        if exchange == "MCX":
            if "SILVER" in s: return "SI=F"
            if "GOLD" in s: return "GC=F"
            if "CRUDE" in s: return "CL=F"
            if "NATURALGAS" in s: return "NG=F"
            return f"{s}.MCX" # Fallback, likely won't work on Yahoo

        # NSE/Indices
        if s == "NIFTY" or s == "NIFTY50" or s == "NIFTY 50": return "^NSEI"
        if s == "BANKNIFTY" or s == "BANK NIFTY": return "^NSEBANK"
        if "INDIA" in s and "VIX" in s: return "^INDIAVIX"

        # Indian Stocks
        # Try to handle common suffixes or missing ones
        if s.endswith(".NS"): return s
        if s.endswith(".BO"): return s
        return f"{s}.NS"

    def _map_interval(self, interval):
        """Map internal interval to yfinance interval."""
        mapping = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "60m": "60m",
            "1h": "1h", "1d": "1d", "day": "1d", "1wk": "1wk", "1mo": "1mo"
        }
        return mapping.get(interval, "1d")

    def get_quote(self, symbol, exchange="NSE"):
        """Mock quote."""
        return {'ltp': 1000.0} # Dummy

    def placesmartorder(self, *args, **kwargs):
        """Mock order placement."""
        return {'status': 'success', 'order_id': 'mock_order_123'}


class ComprehensiveBacktester:
    def __init__(self, strategies_dir):
        self.strategies_dir = strategies_dir
        self.strategies = []
        self.results = []

    def discover_strategies(self):
        """Find all python files in strategies dir with 'generate_signal'."""
        for filename in os.listdir(self.strategies_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                filepath = os.path.join(self.strategies_dir, filename)
                self._load_strategy(filepath)

    def _load_strategy(self, filepath):
        """Load strategy module."""
        try:
            module_name = os.path.basename(filepath).replace('.py', '')
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, 'generate_signal'):
                # Check for strategy symbol preference if any (defaults to NIFTY/SILVER based on name?)
                symbol = "NIFTY"
                exchange = "NSE"

                # Heuristic for symbol
                if "mcx" in module_name.lower():
                    symbol = "SILVERMIC" # Proxy
                    exchange = "MCX"
                elif "bank" in module_name.lower():
                    symbol = "BANKNIFTY"
                    exchange = "NSE_INDEX"
                elif "nifty" in module_name.lower():
                    symbol = "NIFTY"
                    exchange = "NSE_INDEX"

                self.strategies.append({
                    "name": module_name,
                    "module": module,
                    "symbol": symbol,
                    "exchange": exchange,
                    "filepath": filepath
                })
                logger.info(f"Discovered Strategy: {module_name}")
            else:
                logger.debug(f"Skipping {module_name} (no generate_signal)")

        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")

    def run_backtests(self, start_date, end_date):
        """Run backtests for all discovered strategies."""
        # Patch SimpleBacktestEngine to use MockAPIClient?
        # Actually SimpleBacktestEngine takes 'api_key' and creates 'APIClient'.
        # We need to inject MockAPIClient.
        # SimpleBacktestEngine.__init__ creates self.client = APIClient(...)
        # We can monkeypatch APIClient in trading_utils or just subclass SimpleBacktestEngine.

        # Subclassing is cleaner
        class MockBacktestEngine(SimpleBacktestEngine):
            def __init__(self, initial_capital=100000.0):
                super().__init__(initial_capital=initial_capital, api_key="mock")
                self.client = MockAPIClient() # Override client

        engine = MockBacktestEngine()

        for strat in self.strategies:
            logger.info(f"Backtesting {strat['name']} on {strat['symbol']}...")
            try:
                # Some strategies might need specific params injected via generate_signal wrapper
                # But simple_backtest_engine calls generate_signal(df, client, symbol)

                res = engine.run_backtest(
                    strategy_module=strat['module'],
                    symbol=strat['symbol'],
                    exchange=strat['exchange'],
                    start_date=start_date,
                    end_date=end_date,
                    interval="1d" # Default to 1d to ensure data availability
                )

                metrics = res.get('metrics', {})
                self.results.append({
                    "strategy": strat['name'],
                    "symbol": strat['symbol'],
                    "total_return": metrics.get('total_return_pct', 0),
                    "sharpe": metrics.get('sharpe_ratio', 0),
                    "drawdown": metrics.get('max_drawdown_pct', 0),
                    "win_rate": metrics.get('win_rate', 0),
                    "trades": res.get('total_trades', 0),
                    "profit_factor": metrics.get('profit_factor', 0)
                })

            except Exception as e:
                logger.error(f"Backtest failed for {strat['name']}: {e}", exc_info=True)

    def save_results(self):
        """Save results to JSON and Markdown."""
        # Sort by Sharpe
        self.results.sort(key=lambda x: (x['sharpe'], x['total_return']), reverse=True)

        # JSON
        with open("leaderboard_new.json", "w") as f:
            json.dump(self.results, f, indent=4)

        # Markdown
        md = "# Comprehensive Strategy Leaderboard\n\n"
        md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        md += "| Rank | Strategy | Symbol | Sharpe | Return % | Drawdown % | Win Rate % | Trades | PF |\n"
        md += "|---|---|---|---|---|---|---|---|---|\n"

        for i, r in enumerate(self.results):
            md += f"| {i+1} | {r['strategy']} | {r['symbol']} | {r['sharpe']:.2f} | {r['total_return']:.2f}% | {r['drawdown']:.2f}% | {r['win_rate']:.2f}% | {r['trades']} | {r['profit_factor']:.2f} |\n"

        with open("LEADERBOARD_NEW.md", "w") as f:
            f.write(md)

        logger.info(f"Results saved to LEADERBOARD_NEW.md and leaderboard_new.json")


if __name__ == "__main__":
    strategies_dir = os.path.join(repo_root, "openalgo", "strategies", "scripts")

    # Run for a known past period compatible with Yahoo Finance
    # Using 1d data allows longer history
    start_date = "2023-01-01"
    end_date = "2024-12-31"

    backtester = ComprehensiveBacktester(strategies_dir)
    backtester.discover_strategies()
    backtester.run_backtests(start_date, end_date)
    backtester.save_results()
