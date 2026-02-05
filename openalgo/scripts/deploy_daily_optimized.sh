#!/bin/bash
# Auto-generated deployment script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/'

echo 'Starting optimized strategies...'
nohup python3 openalgo/strategies/scripts/gap_fade_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/gap_fade_strategy_NIFTY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_NIFTY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol RELIANCE --api_key $OPENALGO_APIKEY > openalgo/log/strategies/ai_hybrid_reversion_breakout_RELIANCE.log 2>&1 &
nohup python3 openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py --symbol GOLD --api_key $OPENALGO_APIKEY > openalgo/log/strategies/mcx_commodity_momentum_strategy_GOLD.log 2>&1 &

echo 'Deployment complete.'
