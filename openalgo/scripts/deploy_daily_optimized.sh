#!/bin/bash
# Auto-generated deployment script

echo 'Stopping strategies...'
pkill -f 'python3 openalgo/strategies/scripts/' || true

echo 'Starting optimized strategies...'
nohup python3 openalgo/strategies/scripts/advanced_ml_momentum_strategy.py --symbol TATASTEEL --api_key $OPENALGO_APIKEY > openalgo/log/strategies/advanced_ml_momentum_strategy_TATASTEEL.log 2>&1 &
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_NIFTY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol BANKNIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_BANKNIFTY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/opening_range_breakout.py --symbol CRUDEOIL --api_key $OPENALGO_APIKEY > openalgo/log/strategies/opening_range_breakout_CRUDEOIL.log 2>&1 &
nohup python3 openalgo/strategies/scripts/opening_range_breakout.py --symbol INFY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/opening_range_breakout_INFY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol RELIANCE --api_key $OPENALGO_APIKEY > openalgo/log/strategies/ai_hybrid_reversion_breakout_RELIANCE.log 2>&1 &
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol INFY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/ai_hybrid_reversion_breakout_INFY.log 2>&1 &

echo 'Deployment complete.'
