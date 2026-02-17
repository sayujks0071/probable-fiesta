import pandas as pd
import logging
import re
import os
from datetime import datetime, timedelta
import calendar

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SymbolResolver")

class SymbolResolver:
    def __init__(self, instruments_path=None):
        if instruments_path is None:
            # Default to openalgo/data/instruments.csv
            # We assume we are running from root or openalgo/scripts/
            # Try finding the data dir relative to this file
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data'))
            instruments_path = os.path.join(base_path, 'instruments.csv')

        self.instruments_path = instruments_path
        self.df = pd.DataFrame()
        self.load_instruments()

    def load_instruments(self):
        if os.path.exists(self.instruments_path):
            try:
                self.df = pd.read_csv(self.instruments_path)
                # Ensure expiry is datetime and normalized (no time component)
                if 'expiry' in self.df.columns:
                    self.df['expiry'] = pd.to_datetime(self.df['expiry'], errors='coerce').dt.normalize()

                # Normalize columns if needed
                if 'instrument_type' not in self.df.columns and 'segment' in self.df.columns:
                     self.df['instrument_type'] = self.df['segment'].apply(lambda x: 'FUT' if 'FUT' in str(x) else ('OPT' if 'OPT' in str(x) else 'EQ'))

                logger.info(f"Loaded {len(self.df)} instruments from {self.instruments_path}")
            except Exception as e:
                logger.error(f"Failed to load instruments: {e}")
        else:
            logger.warning(f"Instruments file not found at {self.instruments_path}")

    def resolve(self, config):
        """
        Resolve a strategy config to a tradable symbol.
        Config: {
            'underlying': 'NIFTY',
            'type': 'OPT',
            'expiry_preference': 'WEEKLY',
            'option_type': 'CE',
            'strike_criteria': 'ATM',
            'exchange': 'NFO'
        }
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
            # For validation purposes, return a sample or dict
            return self._resolve_option_validation(config)
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
        elif itype == 'FUT':
            return self._resolve_future(config.get('underlying'), config.get('exchange', 'NSE'))
        else:
            return self._resolve_equity(config.get('underlying'), config.get('exchange', 'NSE'))

    def _resolve_equity(self, symbol, exchange):
        if self.df.empty: return symbol

        # Exact Match on Symbol
        mask = (self.df['symbol'] == symbol) & (self.df['exchange'] == exchange)
        if not self.df[mask].empty:
            return self.df[mask].iloc[0]['symbol']

        # Match on Name
        mask = (self.df['name'] == symbol) & (self.df['instrument_type'] == 'EQ') & (self.df['exchange'] == exchange)
        if not self.df[mask].empty:
            return self.df[mask].iloc[0]['symbol']

        logger.warning(f"Equity {symbol} not found.")
        return symbol

    def _resolve_future(self, underlying, exchange):
        if self.df.empty: return f"{underlying}FUT"

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Filter by Underlying Name & Future Type & Exchange & Future Expiry
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'FUT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        matches = self.df[mask].sort_values('expiry')

        if matches.empty:
            # Fallback: Try symbol starts with underlying
            mask = (self.df['symbol'].str.startswith(underlying)) & \
                   (self.df['instrument_type'] == 'FUT') & \
                   (self.df['exchange'] == exchange) & \
                   (self.df['expiry'] >= now)
            matches = self.df[mask].sort_values('expiry')

        if matches.empty:
            logger.warning(f"No futures found for {underlying}")
            return None

        # MCX MINI Preference Logic (Smallest Lot Size)
        if exchange == 'MCX':
            # If lot_size is available, sort by lot_size ascending to find smallest contract (Micro/Mini)
            if 'lot_size' in matches.columns:
                matches = matches.sort_values('lot_size', ascending=True)
                smallest = matches.iloc[0]
                logger.info(f"Selected MCX contract with smallest lot size ({smallest['lot_size']}): {smallest['symbol']}")
                return smallest['symbol']

            # Fallback to Regex if lot_size missing
            # Identify MINI contracts: usually ends with 'M' before date part or contains 'MINI'
            # Heuristic: Check for 'M' suffix on underlying in symbol (e.g. GOLDM...) vs GOLD...

            # Regex for MCX: underlying + 'M' + date...
            # e.g. GOLDM05FEB26FUT
            mini_regex = re.compile(rf"^{underlying}M\d{{2}}[A-Z]{{3}}\d{{2}}FUT$", re.IGNORECASE)

            # Filter matches that are MINI
            mini_matches = matches[matches['symbol'].apply(lambda x: bool(mini_regex.match(x)))]

            if not mini_matches.empty:
                logger.info(f"Found MCX MINI contract: {mini_matches.iloc[0]['symbol']}")
                return mini_matches.iloc[0]['symbol']

            # Check for explicit 'MINI' in symbol
            mini_matches_explicit = matches[matches['symbol'].str.contains('MINI', case=False)]
            if not mini_matches_explicit.empty:
                 logger.info(f"Found MCX MINI contract (explicit): {mini_matches_explicit.iloc[0]['symbol']}")
                 return mini_matches_explicit.iloc[0]['symbol']

            logger.info(f"No MCX MINI contract found for {underlying}, using standard.")

        # Return nearest expiry (Standard)
        return matches.iloc[0]['symbol']

    def _resolve_option_validation(self, config):
        """
        Validate option availability and return metadata.
        """
        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NFO')
        expiry_pref = config.get('expiry_preference', 'WEEKLY').upper()

        if self.df.empty: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] >= now)

        matches = self.df[mask]

        if matches.empty:
            # Try alias mapping
            if underlying == 'NIFTY 50':
                config['underlying'] = 'NIFTY'
                return self._resolve_option_validation(config)
            if underlying == 'NIFTY BANK':
                config['underlying'] = 'BANKNIFTY'
                return self._resolve_option_validation(config)

            return None

        unique_expiries = sorted(matches['expiry'].unique())
        selected_expiry = self._select_expiry(unique_expiries, expiry_pref)

        if not selected_expiry:
            return None

        return {
            'status': 'valid',
            'expiry': selected_expiry.strftime('%Y-%m-%d'),
            'count': len(matches[matches['expiry'] == selected_expiry])
        }

    def _select_expiry(self, unique_expiries, expiry_pref):
        """
        Select expiry based on preference.
        WEEKLY: Nearest expiry (usually Thursday).
        MONTHLY: Last expiry of the current month cycle.
        """
        if not unique_expiries: return None

        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        valid_expiries = [d for d in unique_expiries if d >= now]

        if not valid_expiries: return None

        nearest = valid_expiries[0]

        if expiry_pref == 'WEEKLY':
            return nearest

        elif expiry_pref == 'MONTHLY':
            # Logic: Find the last expiry of the *nearest month*
            # If nearest is Oct 19, and there is Oct 26, select Oct 26.
            # If nearest is Oct 26 (last one), select Oct 26.
            # If nearest is Nov 2 (and today is Oct 30), select Nov 30 (end of Nov).

            current_target_month = nearest.month
            current_target_year = nearest.year

            # Collect all expiries in this month
            month_expiries = [
                d for d in valid_expiries
                if d.month == current_target_month and d.year == current_target_year
            ]

            if month_expiries:
                return month_expiries[-1] # Last one is Monthly

            return nearest

        return nearest

    def _get_option_symbol(self, config, spot_price):
        if spot_price is None:
            logger.error("Spot price required for option selection")
            return None

        valid = self._resolve_option_validation(config)
        if not valid: return None

        expiry = pd.to_datetime(valid['expiry'])
        underlying = config.get('underlying')
        exchange = config.get('exchange', 'NFO')
        otype = config.get('option_type', 'CE').upper()
        criteria = config.get('strike_criteria', 'ATM').upper()

        mask = (self.df['name'] == underlying) & \
               (self.df['instrument_type'] == 'OPT') & \
               (self.df['exchange'] == exchange) & \
               (self.df['expiry'] == expiry) & \
               (self.df['symbol'].str.endswith(otype))

        chain = self.df[mask].copy()
        if chain.empty: return None

        # Ensure 'strike' column
        if 'strike' not in chain.columns:
            # Try parsing from symbol: NIFTY23OCT19500CE -> 19500
            # Regex: (\d+)(CE|PE)$
            def parse_strike(sym):
                m = re.search(r'(\d+)(CE|PE)$', sym)
                if m: return float(m.group(1))
                return 0.0
            chain['strike'] = chain['symbol'].apply(parse_strike)

        # Sort by strike
        chain = chain.sort_values('strike')
        strikes = sorted(chain['strike'].unique())

        # Find ATM
        # Find strike with minimum absolute difference
        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        atm_index = strikes.index(atm_strike)

        selected_index = atm_index

        if criteria == 'ITM':
            # Call ITM: Lower Strike (index - 1)
            # Put ITM: Higher Strike (index + 1)
            if otype == 'CE':
                selected_index = max(0, atm_index - 1)
            else:
                selected_index = min(len(strikes)-1, atm_index + 1)
        elif criteria == 'OTM':
            # Call OTM: Higher Strike (index + 1)
            # Put OTM: Lower Strike (index - 1)
            if otype == 'CE':
                selected_index = min(len(strikes)-1, atm_index + 1)
            else:
                selected_index = max(0, atm_index - 1)

        selected_strike = strikes[selected_index]

        # Get Symbol
        final_row = chain[chain['strike'] == selected_strike]
        if not final_row.empty:
            return final_row.iloc[0]['symbol']

        return None
