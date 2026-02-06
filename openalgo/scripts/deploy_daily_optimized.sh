#!/bin/bash
# Auto-generated deployment script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/' || true

sleep 2
echo 'Starting optimized strategies...'
nohup python3 openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py --symbol SILVERM --api_key $OPENALGO_APIKEY > openalgo/log/strategies/mcx_commodity_momentum_strategy_SILVERM.log 2>&1 &
sleep 1
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol BANKNIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_BANKNIFTY.log 2>&1 &
sleep 1

echo 'Verifying deployment...'
sleep 2
echo 'Running processes:'
pgrep -a -f 'python3 openalgo/strategies/scripts/'
