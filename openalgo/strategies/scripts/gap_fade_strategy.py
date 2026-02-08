#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
import signal
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
from openalgo.strategies.utils.symbol_resolver import SymbolResolver
import pandas as pd

# Ensure log directory exists
log_dir = project_root / "openalgo" / "strategies" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "gap_fade.log")
    ]
)
logger = logging.getLogger("GapFadeStrategy")

class GapFadeStrategy:
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.pm = PositionManager(f"{symbol}_GapFade")
        self.resolver = SymbolResolver()

    def calculate_adx(self, df, period=14):
        """Calculate ADX indicator."""
        if len(df) < period + 1:
            return 0

        high = df['high']
        low = df['low']
        close = df['close']

        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0

        tr1 = pd.DataFrame({'a': high - low, 'b': abs(high - close.shift(1)), 'c': abs(low - close.shift(1))})
        tr = tr1.max(axis=1)

        atr = tr.rolling(period).mean()

        plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
        minus_di = 100 * (abs(minus_dm).ewm(alpha=1/period).mean() / atr)

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(period).mean()
        return adx.iloc[-1]

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        if not is_market_open("NSE"):
             logger.warning("Market Closed (NSE). Exiting.")
             return

        if self.pm.has_position():
            logger.info("Already have a position. Skipping entry check.")
            return

        # 1. Get Previous Close
        today = datetime.now()
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        # Get daily candles
        df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)

        prev_close = 0
        if not df.empty and len(df) >= 1:
            # Safe logic to find prev close
            # Assuming dataframe is sorted by date
            prev_close = df.iloc[-1]['close']
            # Check if last row is today's incomplete candle
            if pd.to_datetime(df.iloc[-1]['datetime']).date() == today.date():
                if len(df) >= 2:
                    prev_close = df.iloc[-2]['close']
                else:
                    logger.warning("History has today's candle but no previous day.")

        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Prefer quote's close if valid (broker specific)
        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])

        if prev_close == 0:
            logger.error("Could not determine Previous Close.")
            return

        logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # TREND FILTER (ADX)
        # Fetch 1h candles for trend analysis
        df_trend = self.client.history(f"{self.symbol} 50", interval="60m", start_date=(today - timedelta(days=20)).strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d"))
        if not df_trend.empty:
            adx = self.calculate_adx(df_trend)
            logger.info(f"Trend Strength (ADX): {adx:.2f}")
            if adx > 25:
                logger.warning(f"Strong Trend detected (ADX={adx:.2f} > 25). Fading is risky. Skipping.")
                return

        # 2. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL"
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY"
            option_type = "CE"

        # 3. Select Option Strike
        opt_config = {
            'type': 'OPT',
            'underlying': self.symbol,
            'option_type': option_type,
            'exchange': 'NFO',
            'expiry_preference': 'WEEKLY',
            'strike_criteria': 'ATM'
        }

        trade_symbol = self.resolver.get_tradable_symbol(opt_config, spot_price=current_price)
        if not trade_symbol:
             logger.error("Could not resolve option symbol. Aborting.")
             return

        logger.info(f"Signal: Buy {trade_symbol} (Gap Fade)")

        # 4. Check VIX for Sizing
        vix_quote = self.client.get_quote("INDIA VIX", "NSE")
        vix = float(vix_quote['ltp']) if vix_quote and 'ltp' in vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order
        logger.info(f"Executing {option_type} Buy for {qty} qty on {trade_symbol}.")

        resp = self.client.placesmartorder(
            strategy="GapFade",
            symbol=trade_symbol,
            action="BUY", # Options buying
            exchange="NFO",
            price_type="MARKET",
            product="MIS",
            quantity=qty,
            position_size=qty
        )

        if resp and resp.get('status') == 'success':
            self.pm.update_position(qty, current_price, "BUY")
            logger.info(f"Order Success: {resp}")
        else:
            logger.error(f"Order Failed: {resp}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold)
    strategy.execute()

if __name__ == "__main__":
    main()
