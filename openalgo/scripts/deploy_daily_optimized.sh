#!/bin/bash
# Auto-generated deployment script

# Environment Setup
export PYTHONPATH=$PYTHONPATH:$(pwd)
export OPENALGO_HOST='http://127.0.0.1:5001' # Default Kite
# Ensure API Key is set in environment before running this script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/' || true

sleep 2
echo 'Starting optimized strategies...'
echo 'Starting supertrend_vwap_strategy on port 5001...'
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol BANKNIFTY --port 5001 --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_BANKNIFTY.log 2>&1 &
echo 'Starting ai_hybrid_reversion_breakout on port 5002...'
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol RELIANCE --port 5002 --api_key $OPENALGO_APIKEY > openalgo/log/strategies/ai_hybrid_reversion_breakout_RELIANCE.log 2>&1 &
echo 'Starting mcx_commodity_momentum_strategy on port 5001...'
nohup python3 openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py --symbol GOLD --port 5001 --api_key $OPENALGO_APIKEY > openalgo/log/strategies/mcx_commodity_momentum_strategy_GOLD.log 2>&1 &

echo 'Deployment complete. verifying processes...'
sleep 2
pgrep -af 'python3 openalgo/strategies/scripts/'
