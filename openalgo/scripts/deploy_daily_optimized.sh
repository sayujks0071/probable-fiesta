#!/bin/bash
# Auto-generated deployment script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/' || true

export OPENALGO_APIKEY=${OPENALGO_APIKEY:-'demo_key'}

echo 'Starting optimized strategies...'
nohup python3 openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py --symbol CRUDEOIL --underlying CRUDEOIL > openalgo/log/strategies/mcx_commodity_momentum_strategy_CRUDEOIL.log 2>&1 &
echo 'Started mcx_commodity_momentum_strategy'
nohup python3 openalgo/strategies/scripts/gap_fade_strategy.py --symbol NIFTY > openalgo/log/strategies/gap_fade_strategy_NIFTY.log 2>&1 &
echo 'Started gap_fade_strategy'
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY > openalgo/log/strategies/supertrend_vwap_strategy_NIFTY.log 2>&1 &
echo 'Started supertrend_vwap_strategy'

echo 'Deployment complete.'
