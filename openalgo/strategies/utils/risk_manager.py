import os
import json
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
logger = logging.getLogger("RiskManager")

class RiskManager:
    """
    Centralized Risk Manager for OpenAlgo Strategies.
    Tracks daily PnL and enforces limits.
    """
    def __init__(self, capital=100000.0):
        self.capital = float(os.getenv('OPENALGO_CAPITAL', capital))
        self.max_daily_loss_pct = float(os.getenv('OPENALGO_MAX_DAILY_LOSS_PCT', 2.0))
        self.max_daily_loss = self.capital * (self.max_daily_loss_pct / 100.0)

        self.state_dir = Path(__file__).resolve().parent.parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "risk_state.json"

        self.daily_pnl = 0.0
        self.trade_count = 0
        self.last_reset_date = datetime.now().strftime("%Y-%m-%d")

        self.load_state()
        self.check_reset()

    def check_reset(self):
        """Reset stats if it's a new day."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.last_reset_date:
            logger.info(f"New day detected ({today}). Resetting risk stats.")
            self.daily_pnl = 0.0
            self.trade_count = 0
            self.last_reset_date = today
            self.save_state()

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.trade_count = data.get('trade_count', 0)
                    self.last_reset_date = data.get('last_reset_date', datetime.now().strftime("%Y-%m-%d"))
            except Exception as e:
                logger.error(f"Failed to load risk state: {e}")

    def save_state(self):
        try:
            data = {
                'daily_pnl': self.daily_pnl,
                'trade_count': self.trade_count,
                'last_reset_date': self.last_reset_date
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save risk state: {e}")

    def can_trade(self, symbol, quantity, price, side):
        """
        Check if a new trade is allowed.
        """
        self.check_reset()

        # Check Daily Loss Limit
        if self.daily_pnl < -self.max_daily_loss:
            logger.warning(f"RISK CHECK FAILED: Max Daily Loss Hit ({self.daily_pnl:.2f} < -{self.max_daily_loss:.2f})")
            return False

        return True

    def update_pnl(self, realized_pnl):
        """
        Update Daily PnL with realized PnL from a closed trade.
        """
        self.check_reset()
        self.daily_pnl += realized_pnl
        self.trade_count += 1
        self.save_state()
        logger.info(f"Risk State Updated: Daily PnL = {self.daily_pnl:.2f} (Trades: {self.trade_count})")

    def get_stats(self):
        return {
            'daily_pnl': self.daily_pnl,
            'max_daily_loss': self.max_daily_loss,
            'remaining_risk': self.max_daily_loss + self.daily_pnl
        }
