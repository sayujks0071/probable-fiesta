"""
Centralized Constants and Configuration for OpenAlgo Strategies.
This module defines the source of truth for market hours, default risk limits,
and network configuration to ensure consistency across all strategies.
"""

# Market Hours (IST) - Used for checks in trading_utils
NSE_MARKET_OPEN_TIME = "09:15"
NSE_MARKET_CLOSE_TIME = "15:30"

MCX_MARKET_OPEN_TIME = "09:00"
MCX_MARKET_CLOSE_TIME = "23:30"
MCX_MARKET_CLOSE_TIME_SAT = "23:30" # If applicable

# Risk Management Defaults
DEFAULT_MAX_LOSS_PER_TRADE_PCT = 2.0  # Percentage (e.g., 2.0 = 2%)
DEFAULT_MAX_DAILY_LOSS_PCT = 5.0      # Percentage
DEFAULT_EOD_SQUARE_OFF_NSE = "15:15"  # HH:MM
DEFAULT_EOD_SQUARE_OFF_MCX = "23:15"  # HH:MM
DEFAULT_TRADE_COOLDOWN = 300          # Seconds

# API & Networking
DEFAULT_API_TIMEOUT = 30 # Seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 2 # Seconds

# Brokers
BROKER_KITE_PORT = 5001
BROKER_DHAN_PORT = 5002
