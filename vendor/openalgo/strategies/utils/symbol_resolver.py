import pandas as pd
import logging
from datetime import datetime, timedelta
import os
import re

logger = logging.getLogger("SymbolResolver")

class SymbolResolver:
    def __init__(self, instruments_path=None):
        if instruments_path is None:
            # Default to openalgo/data/instruments.csv
            # Adjust path relative to this file location in vendor/openalgo/strategies/utils/
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data'))
            instruments_path = os.path.join(base_path, 'instruments.csv')

        self.instruments_path = instruments_path
        self.df = pd.DataFrame()
        self.load_instruments()

    def load_instruments(self):
        if os.path.exists(self.instruments_path):
            try:
                self.df = pd.read_csv(self.instruments_path)
                # Ensure expiry is datetime
                if 'expiry' in self.df.columns:
                    self.df['expiry'] = pd.to_datetime(self.df['expiry'], errors='coerce')

                # Normalize columns
                if 'instrument_type' not in self.df.columns and 'segment' in self.df.columns:
                     # Map segment to instrument_type if missing (fallback)
                     self.df['instrument_type'] = self.df['segment'].apply(lambda x: 'FUT' if 'FUT' in str(x) else ('OPT' if 'OPT' in str(x) else 'EQ'))

                # Ensure lot_size is numeric
                if 'lot_size' in self.df.columns:
                    self.df['lot_size'] = pd.to_numeric(self.df['lot_size'], errors='coerce')

                logger.info(f"Loaded {len(self.df)} instruments from {self.instruments_path}")
            except Exception as e:
                logger.error(f"Failed to load instruments: {e}")
        else:
            logger.warning(f"Instruments file not found at {self.instruments_path}")

    def resolve(self, config):
        """
        Resolve a strategy config to a tradable symbol or list of candidates.
        Used primarily for validation during Daily Prep.
        """
        itype = config.get('type', 'EQUITY').upper()
        underlying = config.get('underlying')
        if not underlying:
            underlying = config.get('symbol')

        exchange = config.get('exchange', 'NSE')

        if itype == 'EQUITY':
            return self._resolve_equity(underlying, exchange)
        elif itype == 'FUT':
            return self._resolve_future(underlying, exchange)
        elif itype == 'OPT':
            return self._resolve_option(config)
        else:
            logger.error(f"Unknown instrument type: {itype}")
            return None

    def get_tradable_symbol(self, config, spot_price=None):
        """
        Get a specific tradable symbol for execution.
        For Options, requires spot_price to determine Strike if 'ATM/ITM/OTM' is used.
        """
        itype = config.get('type', 'EQUITY').upper()

        if itype == 'OPT':
            return self._get_option_symbol(config, spot_price)
        else:
            # For Equity/Futures, resolve returns the specific symbol
            return self.resolve(config)

    def _resolve_equity(self, symbol, exchange):
        if self.df.empty: return symbol

        # Simple existence check
        mask = (self.df['name'] == symbol) & (self.df['instrument_type'] == 'EQ') & (self.df['exchange'] == exchange)
        matches = self.df[mask]

        if not matches.empty:
            return matches.iloc[0]['symbol']

        # Try direct symbol match
        mask = (self.df['symbol'] == symbol) & (self.df['exchange'] == exchange)
        matches = self.df[mask]
        if not matches.empty:
            return matches.iloc[0]['symbol']

        logger.warning(f"Equity {symbol} not found in master list")
        return symbol

    def _resolve_future(self, underlying, exchange):
        if self.df.empty: return f"{underlying}FUT"

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Filter for Futures of this underlying
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'FUT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        matches = self.df[mask].sort_values('expiry')

        if matches.empty:
            # Try searching by symbol if name match fails
            mask_sym = (self.df['symbol'].str.startswith(underlying)) & \
                       (self.df['instrument_type'] == 'FUT') & \
                       (self.df['exchange'] == exchange) & \
                       (self.df['expiry'] >= now)
            matches = self.df[mask_sym].sort_values('expiry')

            if matches.empty:
                logger.warning(f"No futures found for {underlying}")
                return None

        # MCX Logic: Prefer MINI
        if exchange == 'MCX':
            # 1. Identify "Mini" contracts via Lot Size or Symbol Name
            # Assuming we want smallest lot size if available, or specifically 'M'/'MINI' pattern

            # Check by Symbol Name pattern
            mini_pattern = r'(?:{}M|{}MINI)'.format(underlying, underlying)
            mini_matches = matches[matches['symbol'].str.contains(mini_pattern, regex=True, flags=re.IGNORECASE)]

            if not mini_matches.empty:
                logger.info(f"Found MCX MINI contract (by Name) for {underlying}: {mini_matches.iloc[0]['symbol']}")
                return mini_matches.iloc[0]['symbol']

            # Check by Lot Size (if available) - Find smallest > 0
            if 'lot_size' in matches.columns:
                valid_lots = matches[matches['lot_size'] > 0]
                if not valid_lots.empty:
                    # Sort by lot size ascending
                    sorted_by_lot = valid_lots.sort_values('lot_size')
                    # But we also want nearest expiry.
                    # Strategy: Take nearest 2 expiries, pick smallest lot among them?
                    # Or just pick absolute smallest lot available?
                    # Usually MINI contracts exist for near months.

                    min_lot = sorted_by_lot.iloc[0]['lot_size']
                    min_lot_matches = matches[matches['lot_size'] == min_lot]

                    if not min_lot_matches.empty:
                        logger.info(f"Found MCX Smallest Contract (Lot: {min_lot}) for {underlying}: {min_lot_matches.iloc[0]['symbol']}")
                        return min_lot_matches.iloc[0]['symbol']

            logger.info(f"No MCX MINI contract found for {underlying}, falling back to standard.")

        # Return nearest expiry
        return matches.iloc[0]['symbol']

    def _resolve_option(self, config):
        underlying = config.get('underlying')
        option_type = config.get('option_type', 'CE').upper()
        expiry_pref = config.get('expiry_preference', 'WEEKLY').upper()
        exchange = config.get('exchange', 'NFO')

        if self.df.empty: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        # Pre-filter by Option Type
        if option_type:
             mask &= self.df['symbol'].str.endswith(option_type)

        matches = self.df[mask].copy()

        if matches.empty:
            # Try name mapping (e.g. NIFTY 50 -> NIFTY)
            if underlying == 'NIFTY 50':
                return self._resolve_option({**config, 'underlying': 'NIFTY'})
            if underlying == 'NIFTY BANK':
                return self._resolve_option({**config, 'underlying': 'BANKNIFTY'})

            logger.warning(f"No options found for {underlying} {option_type}")
            return None

        # Expiry Selection
        unique_expiries = sorted(matches['expiry'].unique())
        if not unique_expiries:
            return None

        selected_expiry = self._select_expiry(unique_expiries, expiry_pref)

        # Filter for this expiry
        matches = matches[matches['expiry'] == selected_expiry]

        if matches.empty:
            return None

        return {
            'status': 'valid',
            'expiry': selected_expiry.strftime('%Y-%m-%d'),
            'sample_symbol': matches.iloc[0]['symbol'],
            'count': len(matches)
        }

    def _select_expiry(self, unique_expiries, expiry_pref):
        """
        Selects the correct expiry date from a list of sorted future dates.
        unique_expiries: List of datetime objects, sorted ascending.
        """
        if not unique_expiries: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Filter out past expiries just in case
        future_expiries = [d for d in unique_expiries if d >= now]
        if not future_expiries:
            return unique_expiries[-1] # Fallback to last known (even if past? shouldn't happen due to query)

        if expiry_pref == 'WEEKLY':
            # Simply the nearest one
            return future_expiries[0]

        elif expiry_pref == 'MONTHLY':
            # Logic: Find the last expiry of the current month.
            # If current month's last expiry is in the past (already handled by future_expiries filter?),
            # or if today is *after* the last Thursday, we need the next month's monthly expiry.

            # Group expiries by (year, month)
            from collections import defaultdict
            expiries_by_month = defaultdict(list)
            for d in future_expiries:
                expiries_by_month[(d.year, d.month)].append(d)

            # Sort months
            sorted_months = sorted(expiries_by_month.keys())

            # Start with nearest month
            for year, month in sorted_months:
                month_expiries = expiries_by_month[(year, month)]
                last_expiry_in_month = month_expiries[-1] # Assuming sorted input

                # If we are looking for a monthly expiry, it is typically the last one of the month
                # (unless it's a 5-week month and logic varies, but usually last Thursday is Monthly)

                return last_expiry_in_month

        return future_expiries[0]

    def _get_option_symbol(self, config, spot_price):
        """
        Find specific option symbol based on spot price and strike criteria (ATM, ITM, OTM).
        """
        if spot_price is None:
            logger.error("Spot price required to resolve Option Symbol")
            return None

        valid_set = self._resolve_option(config)
        if not valid_set or valid_set.get('status') != 'valid':
            return None

        expiry_date = pd.to_datetime(valid_set['expiry'])
        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NFO')
        option_type = config.get('option_type', 'CE').upper()
        strike_criteria = config.get('strike_criteria', 'ATM').upper() # ATM, ITM, OTM

        # Filter instruments for this specific expiry
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] == expiry_date) & \
               (self.df['symbol'].str.endswith(option_type))

        chain = self.df[mask].copy()

        if chain.empty:
            return None

        # Extract Strike Price
        if 'strike' not in chain.columns:
            # Try to parse strike from symbol (e.g. NIFTY23OCT19500CE)
            def parse_strike(sym):
                # Flexible regex: digits followed by CE/PE or just digits at end?
                # Usually: SYMBOL DDMMM YY STRIKE TYPE
                # Or: SYMBOL YY M DD STRIKE TYPE
                # Let's rely on finding the longest number sequence before CE/PE
                m = re.search(r'(\d+(?:\.\d+)?)(?:CE|PE)$', sym)
                return float(m.group(1)) if m else 0.0
            chain['strike'] = chain['symbol'].apply(parse_strike)

        # Sort by strike
        chain = chain.sort_values('strike')

        # Find ATM Strike (Closest to Spot)
        chain['diff'] = abs(chain['strike'] - spot_price)
        atm_row = chain.loc[chain['diff'].idxmin()]
        atm_strike = atm_row['strike']

        # Get list of unique strikes
        strikes = sorted(chain['strike'].unique())
        try:
            atm_index = strikes.index(atm_strike)
        except ValueError:
            # Should not happen as we picked from chain
            atm_index = 0

        selected_strike = atm_strike

        # Adjust for ITM/OTM
        step = 1 # Steps away from ATM

        if strike_criteria == 'ITM':
            # Call ITM = Lower Strike, Put ITM = Higher Strike
            if option_type == 'CE':
                idx = max(0, atm_index - step)
            else:
                idx = min(len(strikes)-1, atm_index + step)
            selected_strike = strikes[idx]

        elif strike_criteria == 'OTM':
            # Call OTM = Higher Strike, Put OTM = Lower Strike
            if option_type == 'CE':
                idx = min(len(strikes)-1, atm_index + step)
            else:
                idx = max(0, atm_index - step)
            selected_strike = strikes[idx]

        # Get final symbol matching the selected strike
        # Note: There might be multiple symbols for same strike (rare, maybe different tokens?)
        # Just pick first
        final_row = chain[chain['strike'] == selected_strike]
        if not final_row.empty:
            return final_row.iloc[0]['symbol']

        return atm_row['symbol']
