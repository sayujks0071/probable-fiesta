#!/bin/bash
# Auto-generated deployment script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/'

echo 'Starting optimized strategies...'
nohup python3 openalgo/strategies/scripts/gap_fade_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/strategies/logs/gap_fade_NIFTY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/strategies/logs/supertrend_vwap_NIFTY.log 2>&1 &

echo 'Deployment complete.'
