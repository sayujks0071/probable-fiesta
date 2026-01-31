import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
import httpx
from datetime import datetime
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    yf = None

# Add utils directory to path for imports
utils_path = Path(__file__).parent.parent / 'utils'
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

try:
    from trading_utils import APIClient
    from symbol_resolver import SymbolResolver
except ImportError:
    try:
        from openalgo.strategies.utils.trading_utils import APIClient
        from openalgo.strategies.utils.symbol_resolver import SymbolResolver
    except ImportError:
        APIClient = None
        SymbolResolver = None

# Configuration
SYMBOL = os.getenv('SYMBOL', None)
GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL', 'GOLD_GLOBAL')
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')

# Strategy Parameters
PARAMS = {
    'divergence_threshold': 3.0, # Percent
    'convergence_threshold': 1.5, # Percent
    'lookback_period': 20,
    'multiplier': 1.0, # Conversion multiplier (Global -> MCX units)
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"MCX_Arbitrage_{SYMBOL}")

class MCXGlobalArbitrageStrategy:
    def __init__(self, symbol, global_symbol, params, api_client=None):
        self.symbol = symbol
        self.global_symbol = global_symbol
        self.params = params
        self.position = 0
        self.data = pd.DataFrame()
        self.api_client = api_client
        self.last_trade_time = 0  # Track last trade time for cooldown
        self.cooldown_seconds = 300  # 5 minutes cooldown between trades

    def fetch_data(self):
        """Fetch live MCX (Kite) and Global (yfinance/Kite) prices."""
        
        try:
            logger.info(f"Fetching data for {self.symbol} vs {self.global_symbol}...")
            
            mcx_price = 0.0
            global_price_inr = 0.0

            # 1. Fetch MCX Price (REAL)
            if self.api_client:
                mcx_quote = self.api_client.get_quote(self.symbol, exchange="MCX")
                if mcx_quote and 'ltp' in mcx_quote:
                    mcx_price = float(mcx_quote['ltp'])
                else:
                     logger.warning(f"Could not fetch MCX quote for {self.symbol}. Using fallback/last known.")
                     # If data exists, use last
                     if not self.data.empty: mcx_price = self.data.iloc[-1]['mcx_price']
            
            if mcx_price == 0.0 and self.api_client:
                 raise RuntimeError(f"Cannot fetch MCX price for {self.symbol}")

            # 2. Fetch Global Price
            # Check if Global Symbol is a Yahoo Ticker (ends with =F or contains =)
            is_yahoo = '=' in self.global_symbol or '^' in self.global_symbol
            
            if is_yahoo and yf:
                # Fetch Global Asset + USDINR
                tickers = f"{self.global_symbol} INR=X"
                data = yf.download(tickers, period="1d", interval="1m", progress=False)

                if not data.empty:
                    # Handle Multi-Index
                    closes = data['Close'] if 'Close' in data.columns else data

                    # Get latest prices
                    g_price = 0.0
                    usd_price = 84.0 # Fallback

                    if self.global_symbol in closes.columns:
                        g_series = closes[self.global_symbol].dropna()
                        if not g_series.empty: g_price = g_series.iloc[-1]

                    if 'INR=X' in closes.columns:
                        u_series = closes['INR=X'].dropna()
                        if not u_series.empty: usd_price = u_series.iloc[-1]

                    if g_price > 0:
                        # Apply Conversion: Global(USD) * USDINR * Multiplier
                        global_price_inr = g_price * usd_price * self.params.get('multiplier', 1.0)
                        logger.info(f"Global: ${g_price:.2f} | USD/INR: {usd_price:.2f} | Conv: {global_price_inr:.2f}")
                    else:
                        logger.warning("Yahoo fetch returned 0/empty for global symbol.")
            
            # Fallback to Kite if not Yahoo or Yahoo failed (and not 0)
            if global_price_inr == 0.0:
                 if self.api_client:
                    global_quote = self.api_client.get_quote(self.global_symbol, exchange="MCX") # Or USE EQUITY?
                    if global_quote and 'ltp' in global_quote:
                        global_price_inr = float(global_quote['ltp'])

            if mcx_price == 0 or global_price_inr == 0:
                logger.warning("Missing price data. Skipping candle.")
                return

            current_time = datetime.now()

            new_row = pd.DataFrame({
                'timestamp': [current_time],
                'mcx_price': [mcx_price],
                'global_price': [global_price_inr]
            })

            self.data = pd.concat([self.data, new_row], ignore_index=True)
            if len(self.data) > 100:
                self.data = self.data.iloc[-100:]

        except RuntimeError:
            # Re-raise RuntimeError (no API client)
            raise
        except Exception as e:
            logger.error(f"Error fetching real data: {e}", exc_info=True)

    def check_signals(self):
        """Check for arbitrage opportunities."""
        if self.data.empty:
            return

        current = self.data.iloc[-1]

        # Calculate Divergence %
        diff = current['mcx_price'] - current['global_price']
        divergence_pct = (diff / current['global_price']) * 100

        logger.info(f"Divergence: {divergence_pct:.2f}% (MCX: {current['mcx_price']:.2f}, Global: {current['global_price']:.2f})")
        
        # Entry Logic
        current_time = time.time()
        time_since_last_trade = current_time - self.last_trade_time
        
        if self.position == 0:
            # Check cooldown period
            if time_since_last_trade < self.cooldown_seconds:
                logger.debug(f"Cooldown active. {self.cooldown_seconds - int(time_since_last_trade)}s remaining before next trade.")
                return
            
            # MCX is Overpriced -> Sell MCX
            if divergence_pct > self.params['divergence_threshold']:
                self.entry("SELL", current['mcx_price'], f"MCX Premium > {self.params['divergence_threshold']}%")

            # MCX is Underpriced -> Buy MCX
            elif divergence_pct < -self.params['divergence_threshold']:
                self.entry("BUY", current['mcx_price'], f"MCX Discount > {self.params['divergence_threshold']}%")

        # Exit Logic
        elif self.position != 0:
            # Check for convergence
            abs_div = abs(divergence_pct)
            if abs_div < self.params['convergence_threshold']:
                side = "BUY" if self.position == -1 else "SELL"
                self.exit(side, current['mcx_price'], "Convergence reached")

    def entry(self, side, price, reason):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        # Place order if API client is available
        order_placed = False
        if self.api_client:
            try:
                response = self.api_client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=1,  # Default quantity for MCX
                    position_size=1
                )
                logger.info(f"[ENTRY] Order placed: {side} {self.symbol} @ {price:.2f} | Order ID: {response.get('orderid', 'N/A') if isinstance(response, dict) else 'N/A'}")
                order_placed = True
            except Exception as e:
                logger.error(f"[ENTRY] Order placement failed: {e}")
        else:
            logger.warning(f"[ENTRY] No API client available - signal logged but order not placed")
        
        # Only update position if order was actually placed successfully
        if order_placed:
            self.position = 1 if side == "BUY" else -1
            self.last_trade_time = time.time()  # Update last trade time

    def exit(self, side, price, reason):
        logger.info(f"SIGNAL: {side} {self.symbol} at {price:.2f} | Reason: {reason}")
        
        # Place exit order if API client is available
        order_placed = False
        if self.api_client:
            try:
                response = self.api_client.placesmartorder(
                    strategy="MCX Global Arbitrage",
                    symbol=self.symbol,
                    action=side,
                    exchange="MCX",
                    price_type="MARKET",
                    product="MIS",
                    quantity=abs(self.position),
                    position_size=0  # Closing position
                )
                logger.info(f"[EXIT] Order placed: {side} {self.symbol} @ {price:.2f} | Order ID: {response.get('orderid', 'N/A') if isinstance(response, dict) else 'N/A'}")
                order_placed = True
            except Exception as e:
                logger.error(f"[EXIT] Order placement failed: {e}")
        else:
            logger.warning(f"[EXIT] No API client available - signal logged but order not placed")
        
        # Only reset position if order was actually placed successfully
        if order_placed:
            self.position = 0
            self.last_trade_time = time.time()  # Update last trade time

    def run(self):
        logger.info(f"Starting MCX Global Arbitrage Strategy for {self.symbol}")
        logger.info("⚠️  IMPORTANT: Strategy uses REAL Kite API data only. No mocked data.")
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        while True:
            try:
                self.fetch_data()
                self.check_signals()
                consecutive_failures = 0  # Reset on success
            except RuntimeError as e:
                # No API client - stop strategy
                logger.error(f"❌ CRITICAL ERROR: {e}")
                logger.error("Strategy stopping. Cannot trade without real API data.")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Error in strategy loop: {e}")
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"❌ Too many consecutive failures ({consecutive_failures}). Stopping strategy.")
                    break
            
            time.sleep(60) # Check every minute for arbitrage

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Global Arbitrage Strategy')
    parser.add_argument('--symbol', type=str, help='MCX Symbol (e.g., GOLDM05FEB26FUT)')
    parser.add_argument('--global_symbol', type=str, help='Global Symbol (e.g., GC=F or GOLD_GLOBAL)')
    parser.add_argument('--multiplier', type=float, default=1.0, help='Unit multiplier (Global -> MCX)')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    if args.multiplier:
        PARAMS['multiplier'] = args.multiplier

    # Use command-line args if provided, otherwise fall back to environment variables
    # OpenAlgo sets environment variables, so this allows both methods
    if args.symbol:
        SYMBOL = args.symbol
    elif os.getenv('SYMBOL'):
        SYMBOL = os.getenv('SYMBOL')
    
    if args.global_symbol:
        GLOBAL_SYMBOL = args.global_symbol
    elif os.getenv('GLOBAL_SYMBOL'):
        GLOBAL_SYMBOL = os.getenv('GLOBAL_SYMBOL')
    
    if args.port:
        API_HOST = f"http://127.0.0.1:{args.port}"
    elif os.getenv('OPENALGO_PORT'):
        API_HOST = f"http://127.0.0.1:{os.getenv('OPENALGO_PORT')}"
    
    if args.api_key:
        API_KEY = args.api_key
    else:
        # Use environment variable (set by OpenAlgo)
        API_KEY = os.getenv('OPENALGO_APIKEY', API_KEY)

    # Validate symbol or resolve default
    if not SYMBOL:
        if SymbolResolver:
            logger.info("Resolving default MCX Gold symbol...")
            resolver = SymbolResolver()
            # Try to resolve generic Gold Mini Future
            SYMBOL = resolver.resolve({'underlying': 'GOLD', 'type': 'FUT', 'exchange': 'MCX'})
            if not SYMBOL:
                 # Fallback
                 SYMBOL = "GOLDM05FEB26FUT"
                 logger.warning(f"Could not resolve symbol, using fallback: {SYMBOL}")
            else:
                 logger.info(f"Resolved to: {SYMBOL}")
        else:
             SYMBOL = "GOLDM05FEB26FUT"
             logger.warning("SymbolResolver not available, using hardcoded fallback.")

    if SYMBOL == "REPLACE_ME" or GLOBAL_SYMBOL == "REPLACE_ME_GLOBAL":
        logger.error(f"❌ Symbol not configured! SYMBOL={SYMBOL}, GLOBAL_SYMBOL={GLOBAL_SYMBOL}")
        logger.error("Please set SYMBOL environment variable or use --symbol argument")
        logger.error("Example: --symbol GOLDM05FEB26FUT --global_symbol GOLD_GLOBAL")
        exit(1)

    # Initialize API client
    api_client = None
    if APIClient:
        try:
            api_client = APIClient(api_key=API_KEY, host=API_HOST)
            logger.info(f"API client initialized for {API_HOST}")
        except Exception as e:
            logger.warning(f"Could not create APIClient: {e}. Strategy will run in signal-only mode.")
    else:
        logger.warning("APIClient not available. Strategy will run in signal-only mode.")

    strategy = MCXGlobalArbitrageStrategy(SYMBOL, GLOBAL_SYMBOL, PARAMS, api_client=api_client)
    strategy.run()
