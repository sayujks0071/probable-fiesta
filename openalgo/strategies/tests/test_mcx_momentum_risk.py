import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

# Patch dependencies
with patch.dict(sys.modules, {'kiteconnect': MagicMock()}):
    from openalgo.strategies.scripts import mcx_commodity_momentum_strategy
    from openalgo.strategies.scripts.mcx_commodity_momentum_strategy import MCXMomentumStrategy

class TestMCXMomentumRisk(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.history.return_value = pd.DataFrame()
        self.params = {
            'adx_threshold': 25,
            'period_rsi': 14,
            'period_atr': 14,
            'period_adx': 14,
            'seasonality_score': 60,
            'global_alignment_score': 60,
            'min_atr': 0
        }

    def test_risk_manager_integration(self):
        # Use patch.object on the module directly
        with patch.object(mcx_commodity_momentum_strategy, 'RiskManager') as MockRM, \
             patch.object(mcx_commodity_momentum_strategy, 'PositionManager') as MockPM:

            # Setup Mocks
            mock_rm_instance = MockRM.return_value
            mock_rm_instance.can_trade.return_value = (True, "OK")
            mock_rm_instance.check_stop_loss.return_value = (False, "OK")
            mock_rm_instance.should_square_off_eod.return_value = False

            mock_pm_instance = MockPM.return_value
            mock_pm_instance.has_position.return_value = False

            # Initialize Strategy
            strategy = MCXMomentumStrategy("GOLD", "key", "host", self.params)

            # Verify RiskManager initialized
            MockRM.assert_called()
            self.assertEqual(strategy.rm, mock_rm_instance)

            # Create Dummy Data for Signal
            df = pd.DataFrame({
                'open': [100]*50, 'high': [105]*50, 'low': [95]*50, 'close': [102]*50,
                'volume': [1000]*50
            })
            df.loc[49, 'close'] = 110
            df.loc[48, 'close'] = 100

            strategy.data = df.copy()
            strategy.data['adx'] = 30
            strategy.data['rsi'] = 60
            strategy.data['atr'] = 5

            # Run check_signals
            strategy.check_signals()

            # Verify can_trade called
            mock_rm_instance.can_trade.assert_called()

            # Verify register_entry called
            mock_rm_instance.register_entry.assert_called()

    def test_risk_manager_blocks_trade(self):
        with patch.object(mcx_commodity_momentum_strategy, 'RiskManager') as MockRM, \
             patch.object(mcx_commodity_momentum_strategy, 'PositionManager') as MockPM:

            mock_rm_instance = MockRM.return_value
            mock_pm_instance = MockPM.return_value

            mock_rm_instance.can_trade.return_value = (False, "Daily Limit Hit")
            mock_pm_instance.has_position.return_value = False

            strategy = MCXMomentumStrategy("GOLD", "key", "host", self.params)

            strategy.data = pd.DataFrame({'close': [100]*50, 'adx': [30]*50, 'rsi': [60]*50})

            strategy.check_signals()

            mock_rm_instance.can_trade.assert_called()
            mock_rm_instance.register_entry.assert_not_called()

if __name__ == '__main__':
    unittest.main()
