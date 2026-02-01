import os
import time
import logging
import pytz
import json
import time as time_module
from pathlib import Path
from datetime import datetime, time as dt_time
import httpx
import pandas as pd
import numpy as np

# Import constants
try:
    from openalgo.strategies.utils.constants import MARKET_HOURS, ENDPOINTS, TIMEOUTS, DEFAULT_API_HOST
except ImportError:
    # Fallback for when running scripts directly
    try:
        from constants import MARKET_HOURS, ENDPOINTS, TIMEOUTS, DEFAULT_API_HOST
    except ImportError:
        # Default fallback if constants file missing
        MARKET_HOURS = {}
        ENDPOINTS = {
            'history': '/api/v1/history',
            'quotes': '/api/v1/quotes',
            'instruments': '/instruments',
            'place_smart_order': '/api/v1/placesmartorder',
            'option_chain': '/api/v1/optionchain',
            'option_greeks': '/api/v1/optiongreeks'
        }
        TIMEOUTS = {'connect': 5.0, 'read': 30.0}
        DEFAULT_API_HOST = 'http://127.0.0.1:5001'

# Configure logging
try:
    from openalgo_observability.logging_setup import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TradingUtils")

def normalize_symbol(symbol):
    """
    Normalize symbol for indices (NIFTY/BANKNIFTY).
    Example: 'NIFTY 50' -> 'NIFTY', 'BANK NIFTY' -> 'BANKNIFTY'
    """
    if not symbol:
        return symbol

    s = symbol.upper().replace(" ", "")

    if "BANK" in s and "NIFTY" in s:
        return "BANKNIFTY"

    if s == "NIFTY" or s == "NIFTY50":
        return "NIFTY"

    return symbol

def is_mcx_market_open():
    """
    Check if MCX market is open (09:00 - 23:30 IST) on weekdays.
    """
    return is_market_open("MCX")

def is_market_open(exchange="NSE"):
    """
    Check if market is open based on exchange.
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    # Check weekend
    if now.weekday() >= 5: # 5=Sat, 6=Sun
        return False

    hours = MARKET_HOURS.get(exchange, MARKET_HOURS.get('NSE')) # Default to NSE
    if not hours:
         # Fallback hardcoded if constants not loaded correctly
         if exchange == "MCX":
             market_start = dt_time(9, 0)
             market_end = dt_time(23, 30)
         else:
             market_start = dt_time(9, 15)
             market_end = dt_time(15, 30)
    else:
        market_start = hours['start']
        market_end = hours['end']

    current_time = now.time()

    return market_start <= current_time <= market_end

def calculate_intraday_vwap(df):
    """
    Calculate VWAP resetting daily.
    Expects DataFrame with 'datetime' (or index), 'close', 'high', 'low', 'volume'.
    """
    df = df.copy()
    
    # Handle datetime column or index
    if isinstance(df.index, pd.DatetimeIndex):
        df['datetime'] = df.index
    elif 'datetime' not in df.columns and 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    elif 'datetime' not in df.columns:
        # If no datetime info, create from index if it's numeric (Unix timestamp)
        if df.index.dtype in ['int64', 'float64']:
            df['datetime'] = pd.to_datetime(df.index, unit='s')
        else:
            df['datetime'] = pd.to_datetime(df.index)

    # Ensure datetime is datetime object
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['date'] = df['datetime'].dt.date

    # Typical Price
    df['tp'] = (df['high'] + df['low'] + df['close']) / 3
    df['pv'] = df['tp'] * df['volume']

    # Group by Date and calculate cumulative sums
    df['cum_pv'] = df.groupby('date')['pv'].cumsum()
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()

    df['vwap'] = df['cum_pv'] / df['cum_vol']

    # Deviation
    df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']

    return df

class PositionManager:
    """
    Persistent position manager to track trades and prevent duplicate orders.
    Saves state to openalgo/strategies/state/{symbol}_state.json
    """
    def __init__(self, symbol):
        self.symbol = symbol
        # Determine state directory relative to this file
        # this file: openalgo/strategies/utils/trading_utils.py
        # target: openalgo/strategies/state/
        self.state_dir = Path(__file__).resolve().parent.parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"{self.symbol}_state.json"

        self.position = 0
        self.entry_price = 0.0
        self.pnl = 0.0

        self.load_state()

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.position = data.get('position', 0)
                    self.entry_price = data.get('entry_price', 0.0)
                    self.pnl = data.get('pnl', 0.0)
                    logger.info(f"Loaded state for {self.symbol}: Pos={self.position} @ {self.entry_price}")
            except Exception as e:
                logger.error(f"Failed to load state for {self.symbol}: {e}")

    def save_state(self):
        try:
            data = {
                'position': self.position,
                'entry_price': self.entry_price,
                'pnl': self.pnl,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state for {self.symbol}: {e}")

    def update_position(self, qty, price, side):
        """
        Update position state.
        side: 'BUY' or 'SELL'
        """
        side = side.upper()

        if side == 'BUY':
            if self.position == 0:
                self.entry_price = price # Long Entry
            elif self.position < 0:
                # Closing Short
                realized_pnl = (self.entry_price - price) * qty
                self.pnl += realized_pnl
                logger.info(f"Closed Short. PnL: {realized_pnl}")

            self.position += qty

        elif side == 'SELL':
            if self.position == 0:
                self.entry_price = price # Short Entry
            elif self.position > 0:
                # Closing Long
                realized_pnl = (price - self.entry_price) * qty
                self.pnl += realized_pnl
                logger.info(f"Closed Long. PnL: {realized_pnl}")

            self.position -= qty

        if self.position == 0:
            self.entry_price = 0.0

        logger.info(f"Position Updated for {self.symbol}: {self.position} @ {self.entry_price}")
        self.save_state()

    def has_position(self):
        return self.position != 0

    def get_pnl(self, current_price):
        """Calculate Unrealized PnL."""
        if self.position == 0:
            return 0.0

        if self.position > 0:
            return (current_price - self.entry_price) * self.position
        else:
            return (self.entry_price - current_price) * abs(self.position)

class SmartOrder:
    """
    Intelligent Order Execution logic.
    Wraps an API client to provide advanced order capabilities.
    """
    def __init__(self, api_client):
        self.client = api_client

    def place_adaptive_order(self, strategy, symbol, action, exchange, quantity,
                           limit_price=None, product='MIS',
                           urgency='MEDIUM'):
        """
        Place an order adapting to market conditions.

        Args:
            urgency: 'LOW' (Passive Limit), 'MEDIUM' (Limit then Market), 'HIGH' (Market)
        """
        logger.info(f"SmartOrder: Placing {action} {quantity} {symbol} (Urgency: {urgency})")

        order_type = "LIMIT" if limit_price else "MARKET"
        price = limit_price if limit_price else 0

        # Override based on urgency
        if urgency == 'HIGH':
            order_type = "MARKET"
            price = 0
        elif urgency == 'LOW' and not limit_price:
            # Low urgency but no limit price provided? Fallback to Market but warn
            logger.warning("SmartOrder: Low urgency requested but no limit price. Using MARKET.")
            order_type = "MARKET"

        try:
            # Use the client's place_smart_order if available (wrapper around placesmartorder)
            # Or use standard place_order
            if hasattr(self.client, 'placesmartorder'):
                return self.client.placesmartorder(
                    strategy=strategy,
                    symbol=symbol,
                    action=action,
                    exchange=exchange,
                    price_type=order_type,
                    product=product,
                    quantity=quantity,
                    position_size=quantity
                )
            else:
                logger.error("SmartOrder: Client does not support 'placesmartorder'")
                return None

        except Exception as e:
            logger.error(f"SmartOrder Failed: {e}")
            return None

    def get_pnl(self, current_price, entry_price, position_size):
        """
        Calculate PnL.
        FIXED: Removed dependency on missing self.position
        """
        if position_size == 0:
            return 0.0

        if position_size > 0:
            return (current_price - entry_price) * position_size
        else:
            return (entry_price - current_price) * abs(position_size)

class APIClient:
    """
    Fallback API Client using httpx.
    """
    def __init__(self, api_key, host=None):
        self.api_key = api_key
        self.host = (host or DEFAULT_API_HOST).rstrip('/')

    def _request(self, method, endpoint, payload=None, timeout=None, max_retries=3):
        """Unified request handler with retry logic"""
        url = f"{self.host}{endpoint}"
        if timeout is None:
            timeout = TIMEOUTS['read']

        for attempt in range(max_retries):
            try:
                if method.lower() == 'post':
                    response = httpx.post(url, json=payload, timeout=timeout)
                else:
                    response = httpx.get(url, params=payload, timeout=timeout)

                if response.status_code == 200:
                    if not response.text or len(response.text.strip()) == 0:
                        raise ValueError("Empty response")

                    try:
                        # Some endpoints like instruments return CSV
                        if endpoint.startswith(ENDPOINTS['instruments']):
                            return response.text

                        data = response.json()
                        return data
                    except ValueError:
                         # Return raw text if JSON parsing fails but status is 200
                         return response.text
                else:
                    logger.warning(f"API {endpoint} failed (HTTP {response.status_code})")

                if attempt < max_retries - 1:
                    time_module.sleep(2 ** attempt)

            except Exception as e:
                logger.warning(f"API Attempt {attempt+1}/{max_retries} failed for {endpoint}: {e}")
                if attempt < max_retries - 1:
                    time_module.sleep(2 ** attempt)
        
        return None

    def history(self, symbol, exchange="NSE", interval="5m", start_date=None, end_date=None, max_retries=3):
        """Fetch historical data"""
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
            "apikey": self.api_key
        }

        data = self._request('post', ENDPOINTS['history'], payload, max_retries=max_retries)

        if data and isinstance(data, dict) and data.get('status') == 'success' and 'data' in data:
            df = pd.DataFrame(data['data'])
            if not df.empty:
                if 'timestamp' in df.columns:
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')

                # Ensure columns exist
                required_cols = ['open', 'high', 'low', 'close', 'volume']
                for col in required_cols:
                    if col not in df.columns:
                        df[col] = 0.0
                return df

        return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE", max_retries=3):
        """Fetch real-time quote"""
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "apikey": self.api_key
        }
        
        data = self._request('post', ENDPOINTS['quotes'], payload, max_retries=max_retries)

        if data and isinstance(data, dict) and data.get('status') == 'success' and 'data' in data:
            quote_data = data['data']
            if 'ltp' in quote_data:
                return quote_data
        
        return None

    def get_instruments(self, exchange="NSE", max_retries=3):
        """Fetch instruments list"""
        endpoint = f"{ENDPOINTS['instruments']}/{exchange}"

        data = self._request('get', endpoint, max_retries=max_retries)

        if data and isinstance(data, str):
            try:
                from io import StringIO
                return pd.read_csv(StringIO(data))
            except Exception as e:
                logger.error(f"Instruments parse error: {e}")

        return pd.DataFrame()

    def placesmartorder(self, strategy, symbol, action, exchange, price_type, product, quantity, position_size):
        """Place smart order"""
        payload = {
            "apikey": self.api_key,
            "strategy": strategy,
            "symbol": symbol,
            "action": action,
            "exchange": exchange,
            "pricetype": price_type,
            "product": product,
            "quantity": str(quantity),
            "position_size": str(position_size),
            "price": "0",
            "trigger_price": "0",
            "disclosed_quantity": "0"
        }
        
        data = self._request('post', ENDPOINTS['place_smart_order'], payload)

        if data:
            if isinstance(data, dict):
                logger.info(f"[ENTRY] Order Placed: {data}")
                return data
            else:
                logger.info(f"[ENTRY] Order Response (Non-JSON): {data}")
                return {"status": "success", "message": "Order placed (non-JSON)"}

        return {"status": "error", "message": "Order failed"}

    def get_option_chain(self, symbol, exchange="NFO", max_retries=3):
        payload = {"symbol": symbol, "exchange": exchange, "apikey": self.api_key}
        data = self._request('post', ENDPOINTS['option_chain'], payload, max_retries=max_retries)
        if data and isinstance(data, dict) and data.get('status') == 'success':
            return data.get('data', {})
        return {}

    def get_option_greeks(self, symbol, expiry=None, max_retries=3):
        payload = {"symbol": symbol, "apikey": self.api_key}
        if expiry: payload['expiry'] = expiry
        data = self._request('post', ENDPOINTS['option_greeks'], payload, max_retries=max_retries)
        if data and isinstance(data, dict) and data.get('status') == 'success':
            return data.get('data', {})
        return {}

    def get_vix(self):
        """Fetch INDIA VIX"""
        quote = self.get_quote("INDIA VIX", "NSE")
        if quote and 'ltp' in quote:
            return float(quote['ltp'])
        return None
