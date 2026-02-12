import pandas as pd
import logging
from datetime import datetime
import os
import re

logger = logging.getLogger("SymbolResolver")

class SymbolResolver:
    def __init__(self, instruments_path=None):
        if instruments_path is None:
            # Default to vendor/openalgo/data/instruments.csv
            # self file is in vendor/openalgo/strategies/utils/
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

                # Normalize columns
                if 'name' not in self.df.columns and 'tradingsymbol' in self.df.columns:
                    self.df['name'] = self.df['tradingsymbol'].apply(lambda x: re.sub(r'\d.*', '', x))

                logger.info(f"Loaded {len(self.df)} instruments from {self.instruments_path}")
            except Exception as e:
                logger.error(f"Failed to load instruments: {e}")
        else:
            logger.warning(f"Instruments file not found at {self.instruments_path}")

    def resolve(self, config):
        """
        Resolve a strategy config to a tradable symbol or list of candidates.
        """
        itype = config.get('type', 'EQUITY').upper()
        underlying = config.get('underlying')
        if not underlying:
            underlying = config.get('symbol')

        exchange = config.get('exchange', 'NSE')

        # Mapping for NIFTY/BANKNIFTY if passed as NIFTY 50 etc
        if underlying == 'NIFTY 50': underlying = 'NIFTY'
        if underlying == 'NIFTY BANK': underlying = 'BANKNIFTY'

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
        """
        itype = config.get('type', 'EQUITY').upper()

        if itype == 'OPT':
            return self._get_option_symbol(config, spot_price)
        else:
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

        # Basic Filter
        mask = (self.df['instrument_type'] == 'FUT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        # Name Filter (Flexible)
        # Check if name column matches underlying OR symbol starts with underlying
        name_mask = (self.df['name'] == underlying) | (self.df['symbol'].str.startswith(underlying))
        mask &= name_mask

        matches = self.df[mask].copy()

        if matches.empty:
            logger.warning(f"No futures found for {underlying}")
            return None

        # MCX MINI Logic
        if exchange == 'MCX':
            # Identify MINI contracts: containing 'M' or 'MINI' or 'MIC' usually followed by digits or end of string
            # Regex: (M|MINI|MIC) followed by digit or end of string, but ensuring it's not just part of the name (e.g. ALUMINIUM)
            # Actually, standard naming: SILVER -> SILVERM, SILVERMIC. GOLD -> GOLDM.

            # Simple heuristic: Sort by lot_size ASC. The smallest lot size is likely the MINI/MICRO.
            matches['lot_size'] = pd.to_numeric(matches['lot_size'], errors='coerce').fillna(999999)
            matches = matches.sort_values(['expiry', 'lot_size'])

            # If multiple contracts exist for the nearest expiry, pick the one with smallest lot size
            nearest_expiry = matches.iloc[0]['expiry']
            same_expiry = matches[matches['expiry'] == nearest_expiry]

            best_match = same_expiry.sort_values('lot_size').iloc[0]

            logger.info(f"MCX Resolution for {underlying}: Selected {best_match['symbol']} (Lot: {best_match['lot_size']})")
            return best_match['symbol']

        # Standard Future (NSE) - just nearest expiry
        matches = matches.sort_values('expiry')
        return matches.iloc[0]['symbol']

    def _resolve_option(self, config):
        underlying = config.get('underlying')
        # Map NIFTY 50 -> NIFTY
        if underlying == 'NIFTY 50': underlying = 'NIFTY'
        if underlying == 'NIFTY BANK': underlying = 'BANKNIFTY'

        option_type = config.get('option_type', 'CE').upper()
        expiry_pref = config.get('expiry_preference', 'WEEKLY').upper()
        exchange = config.get('exchange', 'NFO')

        if self.df.empty: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        if option_type:
             mask &= self.df['symbol'].str.endswith(option_type)

        matches = self.df[mask].copy()

        if matches.empty:
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
        if not unique_expiries: return None

        # 1. Identify the nearest expiry
        nearest_expiry = unique_expiries[0]

        if expiry_pref == 'WEEKLY':
            return nearest_expiry

        elif expiry_pref == 'MONTHLY':
            # Logic: Select the last expiry of the *current month cycle*.
            # The nearest_expiry is the start of our search.
            # We want the last expiry in the month of nearest_expiry.

            target_year = nearest_expiry.year
            target_month = nearest_expiry.month

            same_month_expiries = [
                d for d in unique_expiries
                if d.year == target_year and d.month == target_month
            ]

            if same_month_expiries:
                return same_month_expiries[-1]
            else:
                return nearest_expiry

        return nearest_expiry

    def _get_option_symbol(self, config, spot_price):
        """
        Find specific option symbol based on spot price and strike criteria.
        """
        if spot_price is None:
            logger.error("Spot price required to resolve Option Symbol")
            return None

        valid_set = self._resolve_option(config)
        if not valid_set or valid_set.get('status') != 'valid':
            return None

        expiry_date = pd.to_datetime(valid_set['expiry'])
        underlying = config.get('underlying')
        if underlying == 'NIFTY 50': underlying = 'NIFTY'
        if underlying == 'NIFTY BANK': underlying = 'BANKNIFTY'

        exchange = config.get('exchange', 'NFO')
        option_type = config.get('option_type', 'CE').upper()
        strike_criteria = config.get('strike_criteria', 'ATM').upper()

        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] == expiry_date) & \
               (self.df['symbol'].str.endswith(option_type))

        chain = self.df[mask].copy()

        if chain.empty:
            return None

        # Extract Strike
        if 'strike' not in chain.columns:
            def parse_strike(sym):
                m = re.search(r'(\d+)(CE|PE)$', sym)
                return float(m.group(1)) if m else 0
            chain['strike'] = chain['symbol'].apply(parse_strike)

        chain = chain.sort_values('strike')

        # Find ATM
        chain['diff'] = abs(chain['strike'] - spot_price)
        atm_row = chain.loc[chain['diff'].idxmin()]
        atm_strike = atm_row['strike']

        selected_strike = atm_strike
        strikes = sorted(chain['strike'].unique())
        atm_index = strikes.index(atm_strike)

        if strike_criteria == 'ITM':
            if option_type == 'CE':
                idx = max(0, atm_index - 1)
            else:
                idx = min(len(strikes)-1, atm_index + 1)
            selected_strike = strikes[idx]

        elif strike_criteria == 'OTM':
            if option_type == 'CE':
                idx = min(len(strikes)-1, atm_index + 1)
            else:
                idx = max(0, atm_index - 1)
            selected_strike = strikes[idx]

        final_row = chain[chain['strike'] == selected_strike]
        if not final_row.empty:
            return final_row.iloc[0]['symbol']

        return atm_row['symbol']
