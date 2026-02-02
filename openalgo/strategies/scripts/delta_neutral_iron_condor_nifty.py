#!/usr/bin/env python3
import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
from openalgo.strategies.utils.option_analytics import calculate_greeks, calculate_max_pain
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "openalgo" / "strategies" / "logs" / "iron_condor.log")
    ]
)
logger = logging.getLogger("DeltaNeutralIronCondor")

class DeltaNeutralIronCondor:
    def __init__(self, api_client, symbol="NIFTY", qty=50, max_vix=30, sentiment_score=None, expiry_pref="WEEKLY"):
        self.client = api_client
        self.symbol = symbol
        self.qty = qty
        self.max_vix = max_vix
        self.sentiment_score = sentiment_score
        self.expiry_pref = expiry_pref
        self.pm = PositionManager(f"{symbol}_IC")
        self.resolver = SymbolResolver()

    def get_vix(self):
        q = self.client.get_quote("INDIA VIX", "NSE")
        return float(q['ltp']) if q else 15.0

    def select_strikes(self, spot, vix, chain_data):
        """
        Select strikes based on Delta and VIX.
        """
        # Calculate Max Pain
        max_pain = calculate_max_pain(chain_data)
        logger.info(f"Max Pain Strike: {max_pain}")

        # Use Max Pain as center if close to Spot (within 1%)
        center_price = spot
        if max_pain and abs(spot - max_pain) < (spot * 0.01):
            logger.info("Using Max Pain as Center Price for Strike Selection")
            center_price = max_pain

        # Target Delta for Shorts
        target_delta = 0.20

        # Adjust Wing Width based on VIX
        wing_width = 200 # Default
        if vix >= 20:
            wing_width = 400
            logger.info(f"High VIX ({vix}) -> Widening Wings to {wing_width}")
        elif vix < 12:
            wing_width = 100
            logger.info(f"Low VIX ({vix}) -> Narrowing Wings to {wing_width}")
        else:
            logger.info(f"Medium VIX ({vix}) -> Default Wings {wing_width}")

        # Delta-Based Selection Logic
        ce_short = None
        pe_short = None

        try:
            strikes = sorted([item for item in chain_data if 'strike' in item], key=lambda x: x['strike'])
            best_ce_diff = 1.0
            best_pe_diff = 1.0

            # Assumptions
            T = 7/365.0
            r = 0.06

            for item in strikes:
                strike = item['strike']

                def get_iv(itm, type_key):
                    iv = itm.get(f'{type_key}_iv', 0)
                    if iv == 0:
                        iv = itm.get(type_key, {}).get('iv', 0)
                    if iv > 0:
                         return iv / 100.0
                    return vix / 100.0

                iv_ce = get_iv(item, 'ce')
                ce_greeks = calculate_greeks(spot, strike, T, r, iv_ce, 'ce')
                ce_delta = ce_greeks.get('delta', 0.5)

                if strike > spot and abs(ce_delta - target_delta) < best_ce_diff:
                    best_ce_diff = abs(ce_delta - target_delta)
                    ce_short = strike

                iv_pe = get_iv(item, 'pe')
                pe_greeks = calculate_greeks(spot, strike, T, r, iv_pe, 'pe')
                pe_delta = abs(pe_greeks.get('delta', -0.5))

                if strike < spot and abs(pe_delta - target_delta) < best_pe_diff:
                    best_pe_diff = abs(pe_delta - target_delta)
                    pe_short = strike

            logger.info(f"Delta Search Results: CE Short {ce_short} (Diff: {best_ce_diff:.4f}), PE Short {pe_short} (Diff: {best_pe_diff:.4f})")

        except Exception as e:
            logger.error(f"Delta calculation failed: {e}")
            ce_short = None
            pe_short = None

        # Fallback to ATM + Width
        atm = round(center_price / 50) * 50

        if not ce_short:
            ce_short = atm + wing_width
        if not pe_short:
            pe_short = atm - wing_width

        # Longs (Wings)
        ce_long = ce_short + wing_width
        pe_long = pe_short - wing_width

        return {
            "ce_short": ce_short,
            "pe_short": pe_short,
            "ce_long": ce_long,
            "pe_long": pe_long
        }

    def execute(self):
        logger.info(f"Starting execution for {self.symbol}")

        vix = self.get_vix()
        logger.info(f"Current VIX: {vix}")

        # VIX Filters
        if vix < 12:
            logger.warning(f"VIX {vix} < 12. Too low for Iron Condor (Low Premium/High Gamma Risk). Skipping.")
            return

        if vix > self.max_vix:
            logger.warning(f"VIX {vix} > {self.max_vix}. Reducing Quantity by 50%.")
            self.qty = int(self.qty * 0.5)

        # Sentiment Filter
        if self.sentiment_score is not None:
            logger.info(f"Checking Sentiment Score: {self.sentiment_score}")
            # Score 0 (Negative) to 1 (Positive), 0.5 Neutral
            dist_from_neutral = abs(self.sentiment_score - 0.5)
            if dist_from_neutral > 0.3: # < 0.2 or > 0.8
                logger.warning(f"Sentiment Score {self.sentiment_score} is strongly directional. Iron Condor risk is high. Skipping.")
                return

        quote = self.client.get_quote(f"{self.symbol} 50", "NSE") # Try NIFTY 50
        if not quote:
             quote = self.client.get_quote(self.symbol, "NSE") # Try resolved symbol

        spot = float(quote['ltp']) if quote else 0
        if spot == 0:
            logger.error("Could not fetch spot price.")
            return

        logger.info(f"Spot: {spot}")

        # Fetch Chain
        chain = self.client.get_option_chain(self.symbol)
        if not chain:
            logger.error("Could not fetch option chain.")
            return

        # Resolve Target Expiry using SymbolResolver
        res = self.resolver.resolve({
            'underlying': self.symbol,
            'type': 'OPT',
            'expiry_preference': self.expiry_pref
        })

        target_expiry = None
        if res and isinstance(res, dict) and res.get('status') == 'valid':
            target_expiry = res.get('expiry')
            logger.info(f"Resolved Target Expiry: {target_expiry}")
        else:
            logger.warning("Could not resolve target expiry via SymbolResolver. Using entire chain (Risky).")

        # Filter Chain by Expiry if available
        filtered_chain = chain
        if target_expiry:
            # Assuming chain items have 'expiry' in 'YYYY-MM-DD' or comparable
            # Or we filter using SymbolResolver logic if we had the full instrument list.
            # Here we are filtering the *broker* chain response.
            # If broker chain doesn't have expiry date, we can't filter easily.
            # Assuming broker chain has 'expiry' key.
            filtered_chain = [c for c in chain if c.get('expiry') == target_expiry]
            if not filtered_chain:
                logger.warning(f"No options found for expiry {target_expiry}. Falling back to nearest in chain.")
                filtered_chain = chain
            else:
                logger.info(f"Filtered chain to {len(filtered_chain)} strikes for {target_expiry}")

        strikes = self.select_strikes(spot, vix, filtered_chain)
        logger.info(f"Selected Strikes: {strikes}")

        # Place Orders (Mock)
        logger.info(f"Placing orders for {self.qty} qty...")

        # In real execution, we would resolve specific option symbols for these strikes
        # ce_short_sym = self.resolver.get_tradable_symbol({...})
        # But select_strikes returns strike prices, we need to map back to symbols.
        # Ideally select_strikes should return symbols.

        logger.info("Strategy execution completed (Simulation).")

    def generate_signal(self, df, client=None, symbol=None, params=None):
        """
        Backtesting Interface.
        Iron Condor is complex to backtest in simple engine.
        We return HOLD to avoid errors, or simulate logic.
        """
        return 'HOLD', 0.0, {"reason": "Complex Strategy"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY", help="Index Symbol (e.g. NIFTY)")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--port", type=int, default=5002, help="Broker API Port")
    parser.add_argument("--sentiment_score", type=float, default=None, help="External Sentiment Score (0.0-1.0)")
    parser.add_argument("--expiry", default="WEEKLY", help="Expiry Preference (WEEKLY/MONTHLY)")
    args = parser.parse_args()

    # Resolve Symbol
    resolver = SymbolResolver()
    resolved_symbol = resolver.resolve({'underlying': args.symbol, 'type': 'EQUITY'}) # Resolve underlying name first
    if not resolved_symbol:
         resolved_symbol = args.symbol # Fallback

    logger.info(f"Resolved Underlying: {resolved_symbol}")

    client = APIClient(api_key=os.getenv("OPENALGO_API_KEY"), host=f"http://127.0.0.1:{args.port}")
    strategy = DeltaNeutralIronCondor(client, resolved_symbol, args.qty, sentiment_score=args.sentiment_score, expiry_pref=args.expiry)
    strategy.execute()

# Module level wrapper
def generate_signal(df, client=None, symbol=None, params=None):
    strategy = DeltaNeutralIronCondor(client, symbol)
    return strategy.generate_signal(df, client, symbol, params)

if __name__ == "__main__":
    main()
