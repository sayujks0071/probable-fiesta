#!/bin/bash
# Auto-generated deployment script

# Set Environment
export OPENALGO_APIKEY=${OPENALGO_APIKEY:-'YOUR_API_KEY'}
export OPENALGO_HOST=${OPENALGO_HOST:-'http://127.0.0.1:5001'}

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/' || true

echo 'Starting optimized strategies...'
echo 'Starting supertrend_vwap_strategy on NIFTY'
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY > openalgo/log/strategies/supertrend_vwap_strategy_NIFTY.log 2>&1 &
echo 'Starting mcx_commodity_momentum_strategy on GOLD'
nohup python3 openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py --symbol GOLD > openalgo/log/strategies/mcx_commodity_momentum_strategy_GOLD.log 2>&1 &
echo 'Starting ai_hybrid_reversion_breakout on RELIANCE'
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol RELIANCE > openalgo/log/strategies/ai_hybrid_reversion_breakout_RELIANCE.log 2>&1 &
echo 'Starting gap_fade_strategy on BANKNIFTY'
nohup python3 openalgo/strategies/scripts/gap_fade_strategy.py --symbol BANKNIFTY > openalgo/log/strategies/gap_fade_strategy_BANKNIFTY.log 2>&1 &

echo 'Deployment complete.'
ps aux | grep 'openalgo/strategies/scripts/'
