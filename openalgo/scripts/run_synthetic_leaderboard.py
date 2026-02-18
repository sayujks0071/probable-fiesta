#!/usr/bin/env python3
import os
import sys
import pandas as pd
import numpy as np
import logging
import importlib.util
from datetime import datetime, timedelta

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Setup Utils Path to match strategies
utils_path = os.path.join(repo_root, 'openalgo/strategies/utils')
if utils_path not in sys.path:
    sys.path.insert(0, utils_path)

# Import Utils
from openalgo.strategies.utils.synthetic_data import SyntheticDataGenerator
# We import SimpleBacktestEngine via full path but strategies might import it via 'simple_backtest_engine'
# So we need to be careful.
from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyntheticLeaderboard")

# Configuration
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
        "symbol": "GOLD",
        "exchange": "MCX"
    },
    {
        "name": "AI_Hybrid",
        "file": "openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "symbol": "RELIANCE",
        "exchange": "NSE"
    },
    {
        "name": "ML_Momentum",
        "file": "openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "symbol": "TATASTEEL",
        "exchange": "NSE"
    }
]

def load_strategy_module(filepath):
    try:
        module_name = os.path.basename(filepath).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(repo_root, filepath))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load strategy {filepath}: {e}")
        return None

def main():
    # 1. Generate Synthetic Data
    logger.info("Generating Synthetic Market Data...")
    gen = SyntheticDataGenerator(start_date="2024-01-01", interval_minutes=15)

    # Define Regimes (Shortened for speed)
    regimes = [
        {'type': 'range', 'length': 200, 'volatility': 0.002},
        {'type': 'trend_up', 'length': 300, 'volatility': 0.003},
        {'type': 'volatile', 'length': 200, 'volatility': 0.008},
        {'type': 'trend_down', 'length': 300, 'volatility': 0.003}
    ]

    all_closes = []
    current_price = 100.0
    for r in regimes:
        mu = 0.0
        if r['type'] == 'trend_up': mu = 0.0001
        elif r['type'] == 'trend_down': mu = -0.0001

        segment = []
        dt = 1.0
        sigma = r['volatility']
        price = current_price
        for _ in range(r['length']):
            shock = np.random.normal(0, 1)
            change = (mu - 0.5 * sigma**2) * dt + sigma * shock
            price = price * np.exp(change)
            segment.append(price)

        all_closes.extend(segment)
        current_price = segment[-1]

    # Convert to OHLCV
    n = len(all_closes)
    times = [gen.start_date + i * gen.interval for i in range(n)]

    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.array(all_closes)
    volumes = np.zeros(n)

    opens[0] = closes[0]
    for i in range(1, n):
        opens[i] = closes[i-1] * (1 + np.random.normal(0, 0.0005))
        body_max = max(opens[i], closes[i])
        body_min = min(opens[i], closes[i])
        volatility = 0.005
        highs[i] = body_max * (1 + abs(np.random.normal(0, volatility)))
        lows[i] = body_min * (1 - abs(np.random.normal(0, volatility)))
        volumes[i] = int(10000 * (1 + np.random.normal(0, 0.2)))

    df_synthetic = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    }, index=times)

    # 2. Prepare Mock APIClient Class
    class MockAPIClient:
        def __init__(self, api_key=None, host=None):
            self.api_key = api_key
            self.host = host

        def history(self, symbol, exchange="NSE", interval="5m", start_date=None, end_date=None, max_retries=3):
            symbol_upper = symbol.upper()
            if "VIX" in symbol_upper:
                dates = pd.date_range(start=datetime.now()-timedelta(days=10), periods=100, freq='D')
                return pd.DataFrame({
                    'datetime': dates,
                    'open': 15.0, 'high': 16.0, 'low': 14.0, 'close': 15.0, 'volume': 0
                })

            # For Sector/Index/Stock
            return df_synthetic.tail(200).copy()

        def get_quote(self, symbol, exchange="NSE", max_retries=3):
            return {'ltp': 100.0, 'open': 100.0}

        def get_instruments(self, exchange="NSE", max_retries=3):
            return pd.DataFrame()

        def placesmartorder(self, *args, **kwargs):
            return {"status": "success", "message": "Mock Order Placed"}

        def get_option_chain(self, *args, **kwargs):
            return {}

    # 3. Patch Modules
    # Patch trading_utils.APIClient
    import trading_utils
    trading_utils.APIClient = MockAPIClient

    # Patch SimpleBacktestEngine.load_historical_data
    # We need to patch the one that strategies might import if they import it differently?
    # SimpleBacktestEngine is in simple_backtest_engine.py
    # Strategies import APIClient from trading_utils.
    # Strategies don't import BacktestEngine usually, the runner does.

    def mock_load_data(self_obj, symbol, exchange, start_date, end_date, interval="15m"):
        logger.info(f"Using Synthetic Data for {symbol} ({len(df_synthetic)} bars)")
        return df_synthetic.copy()

    SimpleBacktestEngine.load_historical_data = mock_load_data

    # 4. Run Strategies
    results = []

    # Initialize engine
    # Note: We need to ensure engine uses patched APIClient?
    # Engine imports APIClient from trading_utils inside simple_backtest_engine.py
    # So we need to patch simple_backtest_engine.APIClient if it imported it.

    import simple_backtest_engine
    simple_backtest_engine.APIClient = MockAPIClient

    engine = SimpleBacktestEngine(initial_capital=100000.0)
    # Re-inject client just in case __init__ ran before patch (it didn't here, but safe to be sure)
    engine.client = MockAPIClient()

    for strat_config in STRATEGIES:
        logger.info(f"Testing {strat_config['name']}...")

        module = load_strategy_module(strat_config['file'])
        if not module:
            continue

        try:
            res = engine.run_backtest(
                strategy_module=module,
                symbol=strat_config['symbol'],
                exchange=strat_config['exchange'],
                start_date="2024-01-01",
                end_date="2024-03-01",
                interval="15m"
            )

            metrics = res.get('metrics', {})
            results.append({
                "strategy": strat_config['name'],
                "sharpe": metrics.get('sharpe_ratio', 0),
                "return": metrics.get('total_return_pct', 0),
                "drawdown": metrics.get('max_drawdown_pct', 0),
                "win_rate": metrics.get('win_rate', 0),
                "trades": res.get('total_trades', 0),
                "profit_factor": metrics.get('profit_factor', 0)
            })

        except Exception as e:
            logger.error(f"Error backtesting {strat_config['name']}: {e}", exc_info=True)

    # 5. Print Leaderboard
    results.sort(key=lambda x: x['sharpe'], reverse=True)

    print("\n" + "="*80)
    print(f"{'Strategy':<20} | {'Sharpe':<8} | {'Return %':<10} | {'DD %':<8} | {'Win Rate':<10} | {'Trades':<8}")
    print("-" * 80)
    for r in results:
        print(f"{r['strategy']:<20} | {r['sharpe']:.2f}     | {r['return']:<10.2f} | {r['drawdown']:<8.2f} | {r['win_rate']:<10.2f} | {r['trades']:<8}")
    print("="*80 + "\n")

    # Save to CSV for analysis
    pd.DataFrame(results).to_csv("leaderboard_results.csv", index=False)

if __name__ == "__main__":
    main()
