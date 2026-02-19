#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
    from risk_manager import RiskManager
    from option_analytics import calculate_greeks, calculate_max_pain
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
        from utils.risk_manager import RiskManager
        from utils.option_analytics import calculate_greeks, calculate_max_pain
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
            from openalgo.strategies.utils.risk_manager import RiskManager
            from openalgo.strategies.utils.option_analytics import calculate_greeks, calculate_max_pain
        except ImportError:
            print("CRITICAL: openalgo package not found.")
            sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DeltaNeutralIronCondor")

class DeltaNeutralIronCondor:
    def __init__(self, api_client, symbol="NIFTY", qty=50, max_vix=30, sentiment_score=None):
        self.client = api_client
        self.symbol = normalize_symbol(symbol)
        self.qty = qty
        self.max_vix = max_vix
        self.sentiment_score = sentiment_score

        # Risk Manager
        self.rm = RiskManager(
            strategy_name=f"IronCondor_{self.symbol}",
            exchange="NSE",
            capital=1000000,
            config={'max_loss_per_trade_pct': 2.0}
        )

    def get_vix(self):
        q = self.client.get_quote("INDIA VIX", "NSE")
        return float(q['ltp']) if q else 15.0

    def select_strikes(self, spot, vix, chain_data):
        """
        Select strikes based on Delta and VIX.
        Returns dictionary with strikes and trading symbols.
        """
        # Filter chain for nearest expiry
        # (Assuming chain_data is already for a specific expiry or we sort/filter here)
        # For simplicity, we assume chain_data is valid.

        # Calculate Max Pain
        try:
            max_pain = calculate_max_pain(chain_data)
            logger.info(f"Max Pain Strike: {max_pain}")
        except:
            max_pain = spot

        center_price = spot
        if max_pain and abs(spot - max_pain) < (spot * 0.01):
            center_price = max_pain

        target_delta = 0.20
        wing_width = 200
        if vix >= 20: wing_width = 400
        elif vix < 12: wing_width = 100

        ce_short_strike = None
        pe_short_strike = None

        # Helper to find symbol
        def find_symbol(strike, type_key):
            for item in chain_data:
                if item.get('strike') == strike:
                    return item.get(type_key, {}).get('symbol')
            return None

        try:
            strikes = sorted([item for item in chain_data if 'strike' in item], key=lambda x: x['strike'])
            best_ce_diff = 1.0
            best_pe_diff = 1.0

            T = 7/365.0
            r = 0.06

            for item in strikes:
                strike = item['strike']

                # Helper for IV
                def get_iv(itm, type_key):
                    iv = itm.get(f'{type_key}_iv', 0)
                    if iv == 0: iv = itm.get(type_key, {}).get('iv', 0)
                    return iv/100.0 if iv > 0 else vix/100.0

                iv_ce = get_iv(item, 'ce')
                ce_greeks = calculate_greeks(spot, strike, T, r, iv_ce, 'ce')
                ce_delta = ce_greeks.get('delta', 0.5)

                if strike > spot and abs(ce_delta - target_delta) < best_ce_diff:
                    best_ce_diff = abs(ce_delta - target_delta)
                    ce_short_strike = strike

                iv_pe = get_iv(item, 'pe')
                pe_greeks = calculate_greeks(spot, strike, T, r, iv_pe, 'pe')
                pe_delta = abs(pe_greeks.get('delta', -0.5))

                if strike < spot and abs(pe_delta - target_delta) < best_pe_diff:
                    best_pe_diff = abs(pe_delta - target_delta)
                    pe_short_strike = strike

        except Exception as e:
            logger.error(f"Delta calculation failed: {e}")

        # Fallback
        atm = round(center_price / 50) * 50
        if not ce_short_strike: ce_short_strike = atm + wing_width
        if not pe_short_strike: pe_short_strike = atm - wing_width

        ce_long_strike = ce_short_strike + wing_width
        pe_long_strike = pe_short_strike - wing_width

        return {
            "ce_short": {"strike": ce_short_strike, "symbol": find_symbol(ce_short_strike, 'ce')},
            "pe_short": {"strike": pe_short_strike, "symbol": find_symbol(pe_short_strike, 'pe')},
            "ce_long": {"strike": ce_long_strike, "symbol": find_symbol(ce_long_strike, 'ce')},
            "pe_long": {"strike": pe_long_strike, "symbol": find_symbol(pe_long_strike, 'pe')}
        }

    def execute(self):
        logger.info(f"Starting execution for {self.symbol}")

        # Risk Check
        can_trade, reason = self.rm.can_trade()
        if not can_trade:
            logger.error(f"Risk Check Failed: {reason}")
            return

        vix = self.get_vix()
        if vix < 12:
            logger.warning(f"VIX {vix} < 12. Skipping.")
            return

        if vix > self.max_vix:
            self.qty = int(self.qty * 0.5)

        if self.sentiment_score is not None:
            dist = abs(self.sentiment_score - 0.5)
            if dist > 0.3:
                logger.warning(f"Sentiment {self.sentiment_score} too directional. Skipping.")
                return

        # Spot Price
        quote = self.client.get_quote(f"{self.symbol}", "NSE") # Using NIFTY/BANKNIFTY
        if not quote: # Try NIFTY 50
             quote = self.client.get_quote("NIFTY 50", "NSE")

        spot = float(quote['ltp']) if quote else 0
        if spot == 0:
            logger.error("Could not fetch spot price.")
            return

        logger.info(f"Spot: {spot}")

        # Chain
        chain = self.client.get_option_chain(self.symbol)
        if not chain:
            logger.error("Could not fetch option chain.")
            return

        legs = self.select_strikes(spot, vix, chain)
        logger.info(f"Selected Legs: {legs}")

        # Validate Symbols
        for key, leg in legs.items():
            if not leg['symbol']:
                logger.error(f"Could not resolve symbol for {key} at strike {leg['strike']}")
                return

        # Execute Legs (Iron Condor: Short Put, Short Call, Long Put, Long Call)
        # Order: Buy Wings first, then Sell Center (Margin Benefit)

        orders = [
            ("ce_long", "BUY"),
            ("pe_long", "BUY"),
            ("ce_short", "SELL"),
            ("pe_short", "SELL")
        ]

        for leg_name, action in orders:
            leg = legs[leg_name]
            symbol = leg['symbol']
            logger.info(f"Placing {action} {self.qty} {symbol} ({leg_name})")

            resp = self.client.placesmartorder(
                strategy=f"IronCondor_{self.symbol}",
                symbol=symbol,
                action=action,
                exchange="NFO",
                price_type="MARKET",
                product="MIS",
                quantity=self.qty,
                position_size=self.qty
            )

            if resp and resp.get('status') == 'success':
                # Register with RM (approximation for options)
                # Ideally RM should handle options specifically, but basic tracking helps
                self.rm.register_entry(symbol, self.qty, 0, "LONG" if action=="BUY" else "SHORT")
            else:
                logger.error(f"Order failed for {symbol}")
                # Logic to unwind if partial fill needed?
                # For now, just logging error.

        logger.info("Strategy execution completed.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--port", type=int, default=5001, help="Broker API Port")
    parser.add_argument("--sentiment_score", type=float, default=None, help="External Sentiment Score (0.0-1.0)")
    args = parser.parse_args()

    api_key = os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: OPENALGO_APIKEY required.")
        sys.exit(1)

    client = APIClient(api_key=api_key, host=f"http://127.0.0.1:{args.port}")
    strategy = DeltaNeutralIronCondor(client, args.symbol, args.qty, sentiment_score=args.sentiment_score)
    strategy.execute()

if __name__ == "__main__":
    main()
