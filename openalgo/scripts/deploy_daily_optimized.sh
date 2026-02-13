#!/bin/bash
# Auto-generated deployment script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/' || true

sleep 2
echo 'Starting optimized strategies...'
echo 'Starting mcx_commodity_momentum_strategy on SILVERMIC'
nohup python3 openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py --symbol SILVERMIC --api_key $OPENALGO_APIKEY > openalgo/log/strategies/mcx_commodity_momentum_strategy_SILVERMIC.log 2>&1 &
echo 'Starting ai_hybrid_reversion_breakout on BANKNIFTY'
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol BANKNIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/ai_hybrid_reversion_breakout_BANKNIFTY.log 2>&1 &
echo 'Starting gap_fade_strategy on NIFTY'
nohup python3 openalgo/strategies/scripts/gap_fade_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/gap_fade_strategy_NIFTY.log 2>&1 &
echo 'Starting advanced_ml_momentum_strategy on RELIANCE'
nohup python3 openalgo/strategies/scripts/advanced_ml_momentum_strategy.py --symbol RELIANCE --api_key $OPENALGO_APIKEY > openalgo/log/strategies/advanced_ml_momentum_strategy_RELIANCE.log 2>&1 &
echo 'Starting supertrend_vwap_strategy on NIFTY'
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_NIFTY.log 2>&1 &

echo 'Deployment complete.'
