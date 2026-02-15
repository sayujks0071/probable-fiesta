import pytest
import os
import json
import time
import pytz
from datetime import datetime
from unittest.mock import MagicMock, patch
from openalgo.strategies.utils.risk_manager import RiskManager, EODSquareOff

# Helper to clean up state file
@pytest.fixture
def risk_manager():
    strategy_name = "TestStrategy"
    # Ensure cleanup before start
    state_file = RiskManager(strategy_name).state_file
    if state_file.exists():
        os.remove(state_file)

    rm = RiskManager(strategy_name, capital=100000)
    yield rm

    # Cleanup after test
    if rm.state_file.exists():
        os.remove(rm.state_file)

def test_initialization(risk_manager):
    assert risk_manager.capital == 100000
    assert risk_manager.daily_pnl == 0.0
    assert risk_manager.is_circuit_breaker_active == False
    assert risk_manager.config['max_daily_loss_pct'] == 5.0

def test_circuit_breaker(risk_manager):
    # Simulate a loss exceeding limit (5% of 100000 = 5000)
    risk_manager.daily_pnl = -5001

    can_trade, reason = risk_manager.can_trade()
    assert can_trade == False
    assert "CIRCUIT BREAKER TRIGGERED" in reason
    assert risk_manager.is_circuit_breaker_active == True

    # Check persistence
    assert risk_manager.state_file.exists()
    with open(risk_manager.state_file, 'r') as f:
        data = json.load(f)
        assert data['circuit_breaker'] == True

@patch('openalgo.strategies.utils.risk_manager.datetime')
def test_trade_cooldown(mock_datetime, risk_manager):
    # Mock time to be 10:00 AM (safe from EOD)
    # We need to ensure timezone awareness is handled if the code expects it
    # The code uses datetime.now(ist).
    # We can just return a naive datetime if the code handles it, or an aware one.
    # risk_manager.py: now = datetime.now(ist)

    # Create a mock aware datetime
    tz = pytz.timezone('Asia/Kolkata')
    mock_now = datetime(2023, 1, 1, 10, 0, 0, tzinfo=tz)
    mock_datetime.now.return_value = mock_now

    risk_manager.config['trade_cooldown_seconds'] = 10
    risk_manager.last_trade_time = time.time()

    can_trade, reason = risk_manager.can_trade()
    assert can_trade == False
    assert "Trade cooldown active" in reason

    # Wait for cooldown
    # Manually adjust last_trade_time to simulate passage of time
    risk_manager.last_trade_time = time.time() - 11
    can_trade, reason = risk_manager.can_trade()
    assert can_trade == True

def test_register_entry_long(risk_manager):
    symbol = "INFY"
    entry_price = 1000.0
    qty = 10

    risk_manager.register_entry(symbol, qty, entry_price, "LONG")

    pos = risk_manager.positions[symbol]
    assert pos['qty'] == 10
    assert pos['entry_price'] == 1000.0
    assert pos['side'] == "LONG"
    # Default SL 2% -> 980
    assert pos['stop_loss'] == 980.0
    assert pos['trailing_stop'] == 980.0

def test_register_entry_short(risk_manager):
    symbol = "INFY"
    entry_price = 1000.0
    qty = 10

    risk_manager.register_entry(symbol, qty, entry_price, "SHORT")

    pos = risk_manager.positions[symbol]
    assert pos['qty'] == -10
    assert pos['entry_price'] == 1000.0
    assert pos['side'] == "SHORT"
    # Default SL 2% -> 1020
    assert pos['stop_loss'] == 1020.0
    assert pos['trailing_stop'] == 1020.0

def test_check_stop_loss_long(risk_manager):
    risk_manager.register_entry("INFY", 10, 1000.0, "LONG")

    # Price drops to 990 (Above SL 980)
    hit, reason = risk_manager.check_stop_loss("INFY", 990)
    assert hit == False

    # Price drops to 980 (Hit SL)
    hit, reason = risk_manager.check_stop_loss("INFY", 980)
    assert hit == True
    assert "STOP LOSS HIT" in reason

def test_trailing_stop_long(risk_manager):
    risk_manager.register_entry("INFY", 10, 1000.0, "LONG")
    # SL starts at 980

    # Price moves up to 1100
    # New trailing stop should be 1100 * (1 - 0.015) = 1083.5
    # Since 1083.5 > 980, it should update

    new_stop = risk_manager.update_trailing_stop("INFY", 1100)
    assert new_stop == 1100 * (1 - 0.015)
    assert risk_manager.positions["INFY"]['trailing_stop'] == new_stop

def test_trailing_stop_short(risk_manager):
    risk_manager.register_entry("INFY", 10, 1000.0, "SHORT")
    # SL starts at 1020 (2%)

    # Price moves down to 900
    # New trailing stop should be 900 * (1 + 0.015) = 913.5
    # Since 913.5 < 1020, it should update

    new_stop = risk_manager.update_trailing_stop("INFY", 900)
    assert new_stop == 900 * (1 + 0.015)
    assert risk_manager.positions["INFY"]['trailing_stop'] == new_stop

def test_register_exit(risk_manager):
    risk_manager.register_entry("INFY", 10, 1000.0, "LONG")

    # Exit at 1100 -> Profit 100 * 10 = 1000
    pnl = risk_manager.register_exit("INFY", 1100)

    assert pnl == 1000.0
    assert risk_manager.daily_pnl == 1000.0
    assert "INFY" not in risk_manager.positions

@patch('openalgo.strategies.utils.risk_manager.datetime')
def test_eod_square_off_check(mock_datetime, risk_manager):
    # Mock time to be before close
    mock_now = datetime(2023, 1, 1, 10, 0, 0) # 10 AM
    mock_datetime.now.return_value = mock_now

    assert risk_manager.should_square_off_eod() == False

    # Mock time to be after close (15:15 default)
    mock_now = datetime(2023, 1, 1, 15, 16, 0)
    mock_datetime.now.return_value = mock_now

    assert risk_manager.should_square_off_eod() == True

def test_eod_square_off_execution(risk_manager):
    risk_manager.register_entry("INFY", 10, 1000.0, "LONG")

    # Mock callback
    mock_exit = MagicMock(return_value={'status': 'success'})

    eod = EODSquareOff(risk_manager, mock_exit)

    # Force time check to pass by mocking internal method
    risk_manager.should_square_off_eod = MagicMock(return_value=True)

    executed = eod.check_and_execute()

    assert executed == True
    mock_exit.assert_called_once_with("INFY", "SELL", 10.0)
    assert "INFY" not in risk_manager.positions # Should be cleared via register_exit
