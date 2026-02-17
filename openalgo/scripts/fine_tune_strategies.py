#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
import itertools

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Import Utils
try:
    from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
    from openalgo.scripts.daily_backtest_leaderboard import load_strategy_module, STRATEGY_MAP, load_active_strategies
except ImportError:
    sys.path.append(os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    sys.path.append(os.path.join(repo_root, 'openalgo', 'scripts'))
    from simple_backtest_engine import SimpleBacktestEngine
    from daily_backtest_leaderboard import load_strategy_module, STRATEGY_MAP, load_active_strategies

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FineTuner")

# Tuning Grids for Common Params
TUNING_GRIDS = {
    "mcx_commodity_momentum_strategy": {
        "period_adx": [10, 14, 18],
        "adx_threshold": [20, 25, 30],
        "period_rsi": [10, 14, 18]
    },
    "ai_hybrid_reversion_breakout": {
        "rsi_lower": [25, 30, 35],
        "rsi_upper": [65, 70, 75],
        "stop_pct": [0.8, 1.0, 1.5]
    },
    "supertrend_vwap_strategy": {
        "quantity": [25, 50], # Just sizing check
        # "multiplier": [2.0, 3.0] # If supported
    }
}

def generate_variants(base_params, grid):
    keys = list(grid.keys())
    values = list(grid.values())
    combinations = list(itertools.product(*values))

    variants = []
    for combo in combinations:
        new_params = base_params.copy()
        new_params.update(dict(zip(keys, combo)))
        variants.append(new_params)
    return variants

def run_fine_tuning():
    logger.info("=== STARTING FINE TUNING LOOP ===")

    if not os.path.exists("leaderboard.json"):
        logger.error("leaderboard.json not found. Run backtest first.")
        return

    with open("leaderboard.json", 'r') as f:
        leaderboard = json.load(f)

    if not leaderboard:
        logger.warning("Leaderboard empty.")
        return

    # Top 3
    top_strats = leaderboard[:3]

    configs = load_active_strategies()
    engine = SimpleBacktestEngine(initial_capital=100000.0, api_key="BACKTEST")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    recommendations = []

    for entry in top_strats:
        strat_id = entry['strategy_id']
        strat_name = entry['strategy_type']
        symbol = entry['symbol']
        original_score = entry['rank_score']

        logger.info(f"Tuning {strat_id} ({strat_name})... Current Score: {original_score}")

        if strat_name not in TUNING_GRIDS:
            logger.info(f"No tuning grid for {strat_name}. Skipping.")
            continue

        config = configs.get(strat_id, {})
        base_params = config.get('params', {})

        variants = generate_variants(base_params, TUNING_GRIDS[strat_name])
        logger.info(f"Generated {len(variants)} variants.")

        best_variant = None
        best_score = original_score

        module = load_strategy_module(STRATEGY_MAP[strat_name])
        if not module: continue

        for variant_params in variants:
            try:
                # Monkey Patch Params?
                # SimpleBacktestEngine uses strategy_module.
                # If we modify module attributes? But run_backtest calls generate_signal.
                # The generate_signal wrapper I added to ai_hybrid uses `params` arg if passed?
                # Or merges with default.

                # We need to ensure 'generate_signal' accepts params.
                # In my refactor of mcx/ai_hybrid, I added `params` argument to `generate_signal`.
                # But SimpleBacktestEngine.run_backtest calls:
                # strategy_module.generate_signal(historical_df, client=self.client, symbol=symbol)
                # It does NOT pass params.

                # So I must wrap the module's generate_signal function.

                original_func = module.generate_signal

                def wrapped_gen(df, client=None, symbol=None):
                    # Pass params if supported
                    try:
                        return original_func(df, client, symbol, params=variant_params)
                    except TypeError:
                        # Fallback if params not supported
                        return original_func(df, client, symbol)

                # Create wrapper object
                class ModuleWrapper:
                    pass
                wrapper = ModuleWrapper()
                wrapper.generate_signal = wrapped_gen
                # Copy other attributes
                for attr in dir(module):
                    if not attr.startswith('__'):
                        setattr(wrapper, attr, getattr(module, attr))

                res = engine.run_backtest(
                    strategy_module=wrapper,
                    symbol=symbol,
                    exchange=config.get('exchange', 'NSE'),
                    start_date=start_str,
                    end_date=end_str,
                    interval="15m"
                )

                if res.get('error'): continue

                metrics = res.get('metrics', {})
                sharpe = metrics.get('sharpe_ratio', 0)
                ret = metrics.get('total_return_pct', 0)
                dd = metrics.get('max_drawdown_pct', 0)
                wr = metrics.get('win_rate', 0)

                score = (sharpe * 10) + (ret * 0.5) - (dd * 1.0) + (wr * 0.1)

                if score > best_score:
                    best_score = score
                    best_variant = variant_params
                    logger.info(f"  > Improvement found! Score: {score:.2f} (vs {original_score:.2f}) Params: {variant_params}")

            except Exception as e:
                logger.debug(f"Variant failed: {e}")

        if best_variant:
            improvement = ((best_score - original_score) / abs(original_score)) * 100 if original_score != 0 else 100
            recommendations.append({
                "strategy_id": strat_id,
                "original_score": original_score,
                "new_score": best_score,
                "improvement_pct": improvement,
                "recommended_params": best_variant
            })

    # Generate Report
    md = "# 🎯 Tuning Recommendations\n\n"
    if not recommendations:
        md += "No improvements found for top strategies.\n"
    else:
        for rec in recommendations:
            md += f"### {rec['strategy_id']}\n"
            md += f"- **Score Improvement:** {rec['original_score']} -> {rec['new_score']:.2f} (+{rec['improvement_pct']:.1f}%)\n"
            md += f"- **Recommended Params:**\n"
            md += "```json\n"
            md += json.dumps(rec['recommended_params'], indent=2)
            md += "\n```\n\n"

    with open("TUNING_REPORT.md", "w") as f:
        f.write(md)

    logger.info("Tuning Complete: TUNING_REPORT.md")

if __name__ == "__main__":
    run_fine_tuning()
