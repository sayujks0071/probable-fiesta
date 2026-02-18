#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "openalgo" / "strategies" / "logs" / "gap_fade.log")
    ]
)
logger = logging.getLogger("GapFadeStrategy")

class GapFadeStrategy:
    def __init__(self, api_client, symbol="NIFTY", qty=50, gap_threshold=0.5, override_vix=None, sentiment_score=None):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.gap_threshold = gap_threshold # Percentage
        self.override_vix = override_vix
        self.sentiment_score = sentiment_score
        self.pm = PositionManager(f"{symbol}_GapFade")

    def execute(self):
        logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # 1. Get Previous Close
        # Try getting from quote first (usually reliable for indices)
        quote = self.client.get_quote(f"{self.symbol} 50", "NSE")
        if not quote:
             quote = self.client.get_quote(self.symbol, "NSE")

        if not quote:
            logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])
        prev_close = 0.0

        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])
            logger.info(f"Prev Close from Quote: {prev_close}")
        else:
            # Fallback to history
            today = datetime.now()
            start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
            df = self.client.history(f"{self.symbol} 50", interval="day", start_date=start_date, end_date=end_date)
            if not df.empty and len(df) >= 1:
                # If last row is today (check date), use -2
                last_date = pd.to_datetime(df.iloc[-1]['datetime']).date()
                if last_date == today.date():
                    if len(df) >= 2:
                        prev_close = df.iloc[-2]['close']
                else:
                    prev_close = df.iloc[-1]['close']

            if prev_close == 0:
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

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL" # Futures Sell or PE Buy
            # For options: Buy PE
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY"
            option_type = "CE"

        # 3. Select Option Strike (ATM)
        atm = round(current_price / 50) * 50

        # 4. Check VIX for Sizing
        vix = 15.0
        if self.override_vix:
            vix = self.override_vix
        else:
            vix_quote = self.client.get_quote("INDIA VIX", "NSE")
            vix = float(vix_quote['ltp']) if vix_quote else 15

        qty = self.qty
        if vix > 30:
            qty = int(qty * 0.5)
            logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Check Sentiment
        if self.sentiment_score is not None:
            # If Sentiment matches Gap direction, fading it is risky!
            # Gap UP (Positive) and Sentiment Positive -> Trend Continuation likely. Fade is risky.
            # Gap UP (Positive) and Sentiment Negative -> Fade is good.

            is_gap_up = gap_pct > 0
            is_sentiment_positive = self.sentiment_score > 0.6
            is_sentiment_negative = self.sentiment_score < 0.4

            if is_gap_up and is_sentiment_positive:
                logger.warning("Gap UP with Positive Sentiment. Trend Continuation likely. Skipping Fade.")
                return
            if not is_gap_up and is_sentiment_negative:
                logger.warning("Gap DOWN with Negative Sentiment. Trend Continuation likely. Skipping Fade.")
                return

        # 6. Place Order (Simulation)
        logger.info(f"Executing {option_type} Buy at {atm} for {qty} qty.")
        self.pm.update_position(qty, 100, "BUY") # Mock update

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    parser.add_argument("--vix", type=float, default=None, help="Override VIX")
    parser.add_argument("--sentiment_score", type=float, default=None, help="Sentiment Score")
    args = parser.parse_args()

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = GapFadeStrategy(client, args.symbol, args.qty, args.threshold, override_vix=args.vix, sentiment_score=args.sentiment_score)
    strategy.execute()

if __name__ == "__main__":
    main()
