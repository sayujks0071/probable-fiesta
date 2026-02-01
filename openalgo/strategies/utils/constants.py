#!/usr/bin/env python3
"""
System-wide constants and configuration for OpenAlgo Strategies.
"""

import os
from datetime import time as dt_time

# --- API Configuration ---
API_HOST_KITE = os.getenv('API_HOST_KITE', 'http://127.0.0.1:5001')
API_HOST_DHAN = os.getenv('API_HOST_DHAN', 'http://127.0.0.1:5002')
DEFAULT_API_HOST = API_HOST_KITE  # Default to Kite/Zerodha convention

# API Endpoints
ENDPOINTS = {
    'history': '/api/v1/history',
    'quotes': '/api/v1/quotes',
    'instruments': '/instruments',
    'place_smart_order': '/api/v1/placesmartorder',
    'option_chain': '/api/v1/optionchain',
    'option_greeks': '/api/v1/optiongreeks'
}

# Timeouts (seconds)
TIMEOUTS = {
    'connect': 5.0,
    'read': 30.0,
    'write': 10.0
}

# --- Market Hours ---
MARKET_HOURS = {
    'NSE': {
        'start': dt_time(9, 15),
        'end': dt_time(15, 30),
        'eod_sq_off': dt_time(15, 15)  # 3:15 PM
    },
    'MCX': {
        'start': dt_time(9, 0),
        'end': dt_time(23, 30),
        'eod_sq_off': dt_time(23, 25)  # 11:25 PM
    }
}

# --- Risk Management Defaults ---
DEFAULT_RISK_CONFIG = {
    'max_loss_per_trade_pct': 2.0,
    'max_daily_loss_pct': 5.0,
    'max_position_value': 500000,
    'trade_cooldown_seconds': 300
}
