import sys
import os
import json
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import importlib.util
import itertools

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s') # Cleaner output
logger = logging.getLogger("Tuning")

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.append(repo_root)

# Import SimpleBacktestEngine
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

# MockAPIClient (Simplified version of what was in leaderboard script)
class MockAPIClient:
    def __init__(self):
        self.symbol_map = {
            "NIFTY": "^NSEI",
            "NIFTY 50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "SILVERMIC": "SI=F",
            "SILVER": "SI=F",
            "GOLDM": "GC=F",
            "INDIA VIX": "^INDIAVIX"
        }

    def history(self, symbol, exchange="NSE", interval="60m", start_date=None, end_date=None, **kwargs):
        yf_symbol = self.symbol_map.get(symbol, symbol)
        yf_interval = "1d" if interval in ["day", "1d"] else interval

        try:
            # logger.debug(f"Downloading {yf_symbol} ({interval})")
            df = yf.download(yf_symbol, start=start_date, end=end_date, interval=yf_interval, progress=False, multi_level_index=False)
            if df.empty: return pd.DataFrame()
            df.columns = [c.lower() for c in df.columns]
            if df.index.tz is not None: df.index = df.index.tz_convert(None)

            # Mock Volume for Indexes
            if 'volume' in df.columns and (df['volume'] == 0).all():
                import numpy as np
                df['volume'] = np.random.randint(100000, 200000, size=len(df))

            return df
        except:
            return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE"):
        return {'ltp': 0.0}
    def placesmartorder(self, *args, **kwargs):
        return {"status": "success"}

# Tuning Grids
TUNING_CONFIG = {
    "Gap_Fade": {
        "file": "openalgo/strategies/scripts/gap_fade_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX",
        "grid": {
            "threshold": [0.1, 0.2, 0.3], # Base % threshold
            "gap_threshold_atr_mult": [0.3, 0.5, 0.8],
            "use_atr": [True]
        }
    },
    "SuperTrend_VWAP": {
        "file": "openalgo/strategies/scripts/supertrend_vwap_strategy.py",
        "symbol": "NIFTY",
        "exchange": "NSE_INDEX",
        "grid": {
            "volume_mult": [1.0, 1.2, 1.5],
            "use_trend_filter": [True, False],
            "threshold": [150] # Fixed
        }
    },
    "MCX_Momentum": {
        "file": "openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py",
        "symbol": "SILVERMIC",
        "exchange": "MCX",
        "grid": {
            "adx_threshold": [15, 20, 25],
            "atr_sl_mult": [1.5, 2.0, 3.0],
            "use_volatility_sizing": [True, False]
        }
    }
}

def load_strategy_module(filepath):
    module_name = os.path.basename(filepath).replace('.py', '')
    full_path = os.path.join(repo_root, filepath)
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def run_tuning():
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    engine.client = MockAPIClient()

    start_date = "2024-12-01"
    end_date = "2025-01-31"

    final_results = []

    for strat_name, config in TUNING_CONFIG.items():
        logger.info(f"--- Tuning {strat_name} ---")
        module = load_strategy_module(config['file'])

        # Generate combinations
        keys = list(config['grid'].keys())
        values = list(config['grid'].values())
        combinations = list(itertools.product(*values))

        for combo in combinations:
            params = dict(zip(keys, combo))

            # Wrapper to pass params to module.generate_signal
            class ModuleWrapper:
                def __init__(self, original_module, params):
                    self.mod = original_module
                    self.params = params
                    # Copy attributes needed by Engine (e.g. BREAKEVEN_TRIGGER_R if set on module)
                    # We can iterate over dir(module) but that's messy.
                    # We rely on __getattr__

                    # Special handling for attributes set by wrappers (like ATR_SL_MULTIPLIER)
                    # The wrapper function usually sets them on the instance 'strat'.
                    # But Engine reads them from 'strategy_module' (which is this wrapper).

                    # We need to make sure generate_signal sets them on THIS wrapper or we delegate attribute access?
                    # Engine reads module.ATR_SL_MULTIPLIER.
                    # If we use __getattr__, it reads from original_module.
                    # But original_module attributes are static.
                    # The generate_signal wrapper (function) in the file sets attributes on the 'strat' INSTANCE.
                    # It does NOT set them on the module.

                    # Wait, my generate_signal implementations:
                    # def generate_signal(df, ..., params=None):
                    #    strat = Class(...)
                    #    ...
                    #    return strat.generate_signal(df)

                    # The Engine does:
                    # action, ..., ... = strategy_module.generate_signal(...)
                    # if hasattr(strategy_module, 'ATR_SL_MULTIPLIER'): ...

                    # If 'strategy_module' is my Wrapper, and I implement __getattr__, it goes to 'original_module'.
                    # 'original_module' (the .py file object) does NOT have ATR_SL_MULTIPLIER set dynamically!
                    # The FUNCTION generate_signal in the file creates a `strat` instance.

                    # The Engine expects `strategy_module` to have constants like ATR_SL_MULTIPLIER.
                    # If they are dynamic per backtest, I must set them on THIS wrapper.

                    # `Gap_Fade`: Not used (Hardcoded 1.0 exit in engine if no details? No, uses details['atr']).
                    # `MCX_Momentum`: Sets `ATR_SL_MULTIPLIER` on `strat`.
                    # But engine checks `strategy_module.ATR_SL_MULTIPLIER`.
                    # The `generate_signal` function returns `strat`? No, it returns `action`.

                    # ERROR: The Engine design assumes `strategy_module` has constants.
                    # If `generate_signal` inside the module sets attributes on a local `strat` instance, the Engine NEVER sees them!
                    # The Engine sees `strategy_module` (the file).

                    # So my dynamic parameter tuning for ATR_SL_MULTIPLIER will FAIL unless I set it on the wrapper.

                    # FIX: I must extract the desired attributes from params and set them on this wrapper.
                    if 'atr_sl_mult' in params:
                        self.ATR_SL_MULTIPLIER = params['atr_sl_mult']

                def generate_signal(self, df, client=None, symbol=None):
                    return self.mod.generate_signal(df, client, symbol, params=self.params)

                def __getattr__(self, name):
                    return getattr(self.mod, name)

            wrapper = ModuleWrapper(module, params)

            try:
                # logger.info(f"Testing {params}")
                # Silence stdout if possible? Engine logs a lot.

                res = engine.run_backtest(
                    strategy_module=wrapper,
                    symbol=config['symbol'],
                    exchange=config['exchange'],
                    start_date=start_date,
                    end_date=end_date,
                    interval="60m"
                )

                metrics = res.get('metrics', {})
                trades = res.get('total_trades', 0)
                sharpe = metrics.get('sharpe_ratio', 0)
                ret = metrics.get('total_return_pct', 0)

                if trades > 0:
                    logger.info(f"Params: {params} -> Trades: {trades}, Sharpe: {sharpe:.2f}, Return: {ret:.2f}%")
                    final_results.append({
                        "strategy": strat_name,
                        "params": params,
                        "trades": trades,
                        "sharpe": sharpe,
                        "return": ret,
                        "drawdown": metrics.get('max_drawdown_pct', 0)
                    })

            except Exception as e:
                logger.error(f"Error: {e}")

    # Save results
    with open(os.path.join(repo_root, "openalgo", "log", "tuning_results.json"), "w") as f:
        json.dump(final_results, f, indent=4)

    # Generate Markdown Report
    final_results.sort(key=lambda x: (x['strategy'], x['sharpe']), reverse=True)

    md = "# Tuning Results\n\n"
    md += "| Strategy | Params | Trades | Sharpe | Return % | Max DD % |\n"
    md += "|---|---|---|---|---|---|\n"
    for r in final_results:
         md += f"| {r['strategy']} | `{r['params']}` | {r['trades']} | {r['sharpe']:.2f} | {r['return']:.2f}% | {r['drawdown']:.2f}% |\n"

    with open(os.path.join(repo_root, "openalgo", "log", "FINAL_LEADERBOARD.md"), "w") as f:
        f.write(md)

    logger.info("Tuning Complete. Results in openalgo/log/FINAL_LEADERBOARD.md")

if __name__ == "__main__":
    run_tuning()
