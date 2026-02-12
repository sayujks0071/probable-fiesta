#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, is_market_open
from openalgo.strategies.utils.risk_manager import RiskManager
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

# Configure logging
LOG_DIR = project_root / "openalgo" / "log" / "strategies"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "gap_fade.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("GapFadeStrategy")

class GapFadeStrategy:
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, capital=100000, trend_filter=True):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.trend_filter = trend_filter

        # Risk Manager
        self.rm = RiskManager(f"{symbol}_GapFade", exchange="NSE", capital=capital)

        # Symbol Resolver
        self.resolver = SymbolResolver()

    def get_sma(self, period=200):
        """Calculate SMA for Trend Filter"""
        today = datetime.now()
        start_date = (today - timedelta(days=period * 2)).strftime("%Y-%m-%d") # Fetch ample data
        end_date = today.strftime("%Y-%m-%d")

        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)
        if df.empty or len(df) < period:
            logger.warning(f"Insufficient history for SMA {period}. Found {len(df)} candles.")
            return None

        df['sma'] = df['close'].rolling(window=period).mean()
        return df.iloc[-1]['sma']

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol} (Trend Filter: {self.trend_filter})")

        # Check Risk Manager
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.warning(f"Risk Manager Block: {reason}")
            return

        # 1. Get Previous Close
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0.0
        if not df.empty and len(df) >= 1:
            # Try to get yesterday's close
            last_date = pd.to_datetime(df.iloc[-1]['datetime']).date() if 'datetime' in df.columns else None

            if last_date == today.date() and len(df) > 1:
                prev_close = df.iloc[-2]['close']
            else:
                prev_close = df.iloc[-1]['close']

        # Fallback to Quote
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        if prev_close == 0.0 and 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])

        if prev_close == 0.0:
            logger.error("Could not determine Previous Close.")
            return

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        action = None
        option_type = None

        # Trend Filter Check
        trend_ok = True
        sma_val = 0.0

        if self.trend_filter:
            sma_val = self.get_sma(200)
            if sma_val:
                logger.info(f"SMA 200: {sma_val:.2f}, Current: {current_price}")
            else:
                logger.warning("Could not calculate SMA 200. Skipping Trend Filter check (failing open).")

        # Gap UP -> Fade (Sell) -> Buy PE
        if gap_pct > self.gap_threshold:
            logger.info("Gap UP detected. Looking to FADE (Short).")

            if self.trend_filter and sma_val:
                if current_price > sma_val:
                    # Uptrend. Selling is Counter-Trend.
                    logger.warning("Trend Filter Block: Gap UP in Uptrend. Skipping Short Fade.")
                    trend_ok = False
                else:
                    # Downtrend. Selling is With-Trend.
                    logger.info("Trend Filter Pass: Gap UP in Downtrend.")

            if trend_ok:
                action = "BUY"
                option_type = "PE"

        # Gap DOWN -> Fade (Buy) -> Buy CE
        elif gap_pct < -self.gap_threshold:
            logger.info("Gap DOWN detected. Looking to FADE (Long).")

            if self.trend_filter and sma_val:
                if current_price < sma_val:
                    # Downtrend. Buying is Counter-Trend.
                    logger.warning("Trend Filter Block: Gap DOWN in Downtrend. Skipping Long Fade.")
                    trend_ok = False
                else:
                    # Uptrend. Buying is With-Trend.
                    logger.info("Trend Filter Pass: Gap DOWN in Uptrend.")

            if trend_ok:
                action = "BUY"
                option_type = "CE"

        if not action:
            return

        # 3. Resolve Option Symbol
        atm = round(current_price / 50) * 50

        opt_config = {
            'type': 'OPT',
            'underlying': self.symbol,
            'option_type': option_type,
            'expiry_preference': 'WEEKLY',
            'strike_criteria': 'ATM',
            'exchange': 'NFO'
        }

        strike_symbol = self.resolver.get_tradable_symbol(opt_config, spot_price=current_price)

        if not strike_symbol:
            # Fallback
            month_str = today.strftime('%b').upper() # Jan, Feb -> JAN, FEB
            strike_symbol = f"{self.symbol}{today.strftime('%y')}{month_str}{atm}{option_type}"
            logger.warning(f"Could not resolve option symbol via Resolver. Using fallback: {strike_symbol}")

        logger.info(f"Signal: Buy {option_type} - {strike_symbol} (Gap Fade)")

        # 4. Check VIX for Sizing
        vix = self.client.get_vix() or 15.0

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order via Risk Manager Simulation

        # Simulate Fill
        fill_price = 100.0 # Placeholder

        # Calculate Stop Loss
        stop_loss = self.rm.calculate_stop_loss(fill_price, "LONG")

        self.rm.register_entry(strike_symbol, qty, fill_price, "LONG", stop_loss=stop_loss)
        logger.info(f"Executed {option_type} Buy for {qty} qty @ {fill_price}. Registered with Risk Manager.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    parser.add_argument("--capital", type=float, default=100000, help="Capital for Risk Mgmt")
    parser.add_argument("--no-trend-filter", action="store_true", help="Disable Trend Filter (SMA 200)")
    args = parser.parse_args()

    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        logger.error("OPENALGO_API_KEY environment variable not set.")
        sys.exit(1)

    client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, args.capital, trend_filter=not args.no_trend_filter)
    strategy.execute()

if __name__ == "__main__":
    main()
