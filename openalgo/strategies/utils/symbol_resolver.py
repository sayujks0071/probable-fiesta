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
            # Assuming this file is in strategies/utils/, data is in ../../data/
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data'))
            instruments_path = os.path.join(base_path, 'instruments.csv')

        self.instruments_path = instruments_path
        self.df = pd.DataFrame()
        self.load_instruments()

    def load_instruments(self):
        if os.path.exists(self.instruments_path):
            try:
                self.df = pd.read_csv(self.instruments_path, low_memory=False)
                # Ensure expiry is datetime
                if 'expiry' in self.df.columns:
                    self.df['expiry'] = pd.to_datetime(self.df['expiry'], errors='coerce')

                # Normalize columns if needed
                if 'instrument_type' not in self.df.columns and 'segment' in self.df.columns:
                     # Map segment to instrument_type if missing (fallback)
                     self.df['instrument_type'] = self.df['segment'].apply(lambda x: 'FUT' if 'FUT' in str(x) else ('OPT' if 'OPT' in str(x) else 'EQ'))

                # Create uppercase symbol column for easier matching
                if 'symbol' in self.df.columns:
                    self.df['symbol'] = self.df['symbol'].astype(str).str.upper()
                if 'name' in self.df.columns:
                    self.df['name'] = self.df['name'].astype(str).str.upper()

                logger.info(f"Loaded {len(self.df)} instruments from {self.instruments_path}")
            except Exception as e:
                logger.error(f"Failed to load instruments: {e}")
        else:
            logger.warning(f"Instruments file not found at {self.instruments_path}")

    def validate_symbol(self, symbol):
        """Check if a specific symbol exists in the master list."""
        if self.df.empty: return False
        return not self.df[self.df['symbol'] == symbol].empty

    def resolve(self, config):
        """
        Resolve a strategy config to a tradable symbol.
        For Options, it returns a validation object or sample symbol.
        For Futures/Equity, it returns the specific symbol.
        """
        itype = config.get('type', 'EQUITY').upper()
        underlying = config.get('underlying')
        if not underlying:
            underlying = config.get('symbol')

        # If user provided a specific symbol and no underlying, valid it directly
        if config.get('symbol') and not config.get('underlying'):
             if self.validate_symbol(config.get('symbol')):
                 return config.get('symbol')
             # If invalid, continue to try resolving via underlying if possible (though unlikely)

        exchange = config.get('exchange', 'NSE')

        if itype == 'EQUITY':
            return self._resolve_equity(underlying, exchange)
        elif itype == 'FUT':
            return self._resolve_future(underlying, exchange)
        elif itype == 'OPT':
            return self._resolve_option_descriptor(config)
        else:
            logger.error(f"Unknown instrument type: {itype}")
            return None

    def _resolve_equity(self, symbol, exchange):
        if self.df.empty: return symbol

        # specific symbol match
        mask = (self.df['symbol'] == symbol) & (self.df['exchange'] == exchange)
        if not self.df[mask].empty:
            return symbol

        # Name match
        mask = (self.df['name'] == symbol) & (self.df['instrument_type'] == 'EQ') & (self.df['exchange'] == exchange)
        matches = self.df[mask]

        if not matches.empty:
            return matches.iloc[0]['symbol']

        return None

    def _resolve_future(self, underlying, exchange):
        if self.df.empty: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Filter for Futures of this underlying
        # For MCX, we broaden search to include MINI variants explicitly if standard name used
        if exchange == 'MCX':
             # Try to match Name exactly OR Name + M/MINI/MIC
             # Regex for name matching: ^SILVER$|^SILVERM$|^SILVERMIC$
             name_pattern = r'^({}|{}M|{}MIC|{}MINI)$'.format(underlying, underlying, underlying, underlying)
             mask = (self.df['name'].str.match(name_pattern, case=False)) & \
                    (self.df['instrument_type'] == 'FUT') & \
                    (self.df['exchange'] == exchange) & \
                    (self.df['expiry'] >= now)
        else:
            # Standard exact match for NSE
            mask = (self.df['name'] == underlying) & \
                   (self.df['instrument_type'] == 'FUT') & \
                   (self.df['exchange'] == exchange) & \
                   (self.df['expiry'] >= now)

        matches = self.df[mask].sort_values('expiry')

        if matches.empty:
            # Try searching by symbol prefix if name match fails
            mask_sym = (self.df['symbol'].str.startswith(underlying)) & \
                       (self.df['instrument_type'] == 'FUT') & \
                       (self.df['exchange'] == exchange) & \
                       (self.df['expiry'] >= now)
            matches = self.df[mask_sym].sort_values('expiry')

            if matches.empty:
                logger.warning(f"No futures found for {underlying}")
                return None

        # MCX MINI Logic
        if exchange == 'MCX':
            # Identify current nearest expiry
            # Note: MINI might expire on different day than Standard? Usually same month though.
            # We want the nearest available contract generally.

            # If we have mixed results (SILVER and SILVERM), sort by expiry then by "Is Mini?"

            # Heuristic: Prefer MINI.
            # Check if any match is MINI
            mini_pattern = r'({}M|{}MIC|{}MINI)'.format(underlying, underlying, underlying)
            mini_matches = matches[matches['symbol'].str.contains(mini_pattern, regex=True)]

            if not mini_matches.empty:
                # Get nearest MINI
                best_mini = mini_matches.iloc[0]
                logger.info(f"Found MCX MINI contract for {underlying}: {best_mini['symbol']}")
                return best_mini['symbol']

            # Fallback to nearest standard
            logger.info(f"No MCX MINI contract found for {underlying}, using standard.")
            return matches.iloc[0]['symbol']

        # Return nearest expiry for non-MCX
        return matches.iloc[0]['symbol']

    def _resolve_option_descriptor(self, config):
        """
        Returns a dictionary describing validity and available expiries.
        Does NOT return a specific symbol because Option requires Strike (calculated at runtime usually).
        """
        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NFO')
        expiry_pref = config.get('expiry_preference', 'WEEKLY').upper()

        if self.df.empty: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Filter Options for Underlying
        # Use name matching
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        matches = self.df[mask].copy()

        if matches.empty:
            # Mapping fallback
            if underlying == 'NIFTY 50' or underlying == 'NIFTY':
                mapped = 'NIFTY'
            elif underlying == 'NIFTY BANK' or underlying == 'BANKNIFTY':
                mapped = 'BANKNIFTY'
            else:
                mapped = None

            if mapped and mapped != underlying:
                mask = (self.df['name'] == mapped) & \
                       (self.df['instrument_type'] == 'OPT') & \
                       (self.df['exchange'] == exchange) & \
                       (self.df['expiry'] >= now)
                matches = self.df[mask].copy()

        if matches.empty:
            return None

        unique_expiries = sorted(matches['expiry'].unique())
        selected_expiry = self._select_expiry(unique_expiries, expiry_pref)

        # Get a sample symbol (first one)
        sample = matches[matches['expiry'] == selected_expiry].iloc[0]['symbol']
        return {
            'status': 'valid',
            'expiry': selected_expiry.strftime('%Y-%m-%d'),
            'underlying': underlying,
            'exchange': exchange,
            'count': len(matches[matches['expiry'] == selected_expiry]),
            'sample_symbol': sample
        }

    def _select_expiry(self, unique_expiries, expiry_pref):
        if not unique_expiries: return None
        nearest_expiry = unique_expiries[0]

        if expiry_pref == 'WEEKLY':
            return nearest_expiry

        elif expiry_pref == 'MONTHLY':
            # Find the last expiry of the current month cycle
            # Logic: If nearest is Oct 26 (Monthly), and there are Nov expiries, we want Oct 26.
            # If nearest is Oct 19 (Weekly), we want Oct 26 (Monthly).

            # Get month of nearest expiry
            target_year = nearest_expiry.year
            target_month = nearest_expiry.month

            same_month_expiries = [
                d for d in unique_expiries
                if d.year == target_year and d.month == target_month
            ]

            if same_month_expiries:
                return same_month_expiries[-1] # Last one is usually monthly
            else:
                return nearest_expiry

        return nearest_expiry

    def get_tradable_option_symbol(self, config, spot_price):
        """
        Get specific option symbol for execution.
        """
        if spot_price is None: return None

        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NFO')
        option_type = config.get('option_type', 'CE').upper() # or PE
        strike_criteria = config.get('strike_criteria', 'ATM').upper() # ATM, ITM, OTM

        # 1. Resolve Expiry First
        desc = self._resolve_option_descriptor(config)
        if not desc or desc['status'] != 'valid':
            return None

        expiry_date = pd.to_datetime(desc['expiry'])

        # 2. Filter chain
        # Try name match first
        name_match = underlying
        if underlying == 'NIFTY 50': name_match = 'NIFTY'
        if underlying == 'NIFTY BANK': name_match = 'BANKNIFTY'

        mask = (self.df['name'] == name_match) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] == expiry_date) & \
               (self.df['symbol'].str.endswith(option_type))

        chain = self.df[mask].copy()

        if chain.empty:
            return None

        # 3. Determine Strike
        # If strike column missing, extract from symbol
        if 'strike' not in chain.columns:
            chain['strike'] = chain['symbol'].apply(self._extract_strike)

        # Sort
        chain = chain.sort_values('strike')

        # Find ATM
        chain['diff'] = abs(chain['strike'] - spot_price)
        atm_idx = chain['diff'].idxmin()
        atm_strike = chain.loc[atm_idx, 'strike']

        # Select Strike based on criteria
        strikes = sorted(chain['strike'].unique())
        atm_pos = strikes.index(atm_strike)

        selected_strike = atm_strike

        if strike_criteria == 'ITM':
            # Call ITM = Lower, Put ITM = Higher
            if option_type == 'CE':
                idx = max(0, atm_pos - 1)
            else:
                idx = min(len(strikes)-1, atm_pos + 1)
            selected_strike = strikes[idx]

        elif strike_criteria == 'OTM':
             # Call OTM = Higher, Put OTM = Lower
            if option_type == 'CE':
                idx = min(len(strikes)-1, atm_pos + 1)
            else:
                idx = max(0, atm_pos - 1)
            selected_strike = strikes[idx]

        # Return symbol
        final_row = chain[chain['strike'] == selected_strike]
        if not final_row.empty:
            return final_row.iloc[0]['symbol']

        return chain.loc[atm_idx, 'symbol']

    def _extract_strike(self, symbol):
        # NIFTY23OCT19500CE -> 19500
        # CRUDEOIL23OCT6500CE -> 6500
        try:
            m = re.search(r'(\d+)(CE|PE)$', symbol)
            if m:
                return float(m.group(1))
            return 0.0
        except:
            return 0.0
