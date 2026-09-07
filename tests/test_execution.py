import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from config import RiskConfig
from execution import ExecutionEngine, ExecutionError


def make_execution(mock_kite, **overrides):
    cfg = RiskConfig(exchange="NSE", product="MIS", max_slippage_pct=0.2, **overrides)
    return ExecutionEngine(mock_kite, cfg), cfg


def test_enter_confirms_fill_and_returns_price(mock_kite):
    execution, cfg = make_execution(mock_kite)
    mock_kite.next_fill_price = 501.5
    fill = execution.enter("TESTSYM", "LONG", 100, expected_price=500.0)
    assert fill["average_price"] == 501.5
    assert fill["status"] == "COMPLETE"


def test_enter_places_protective_gtt(mock_kite):
    execution, cfg = make_execution(mock_kite)
    mock_kite.next_fill_price = 500.0
    fill = execution.enter("TESTSYM", "LONG", 100, expected_price=500.0, stop=495.0, target=510.0)
    assert fill["gtt_trigger_id"] is not None
    assert len(mock_kite.gtts) == 1


def test_enter_without_stop_target_skips_gtt(mock_kite):
    execution, cfg = make_execution(mock_kite)
    fill = execution.enter("TESTSYM", "LONG", 100, expected_price=500.0)
    assert fill["gtt_trigger_id"] is None
    assert len(mock_kite.gtts) == 0


def test_rejected_order_raises_execution_error(mock_kite):
    execution, cfg = make_execution(mock_kite)
    mock_kite.next_order_status = "REJECTED"
    with pytest.raises(ExecutionError):
        execution.enter("TESTSYM", "LONG", 100, expected_price=500.0)


def test_cancel_backstop_removes_gtt(mock_kite):
    execution, cfg = make_execution(mock_kite)
    fill = execution.enter("TESTSYM", "LONG", 100, expected_price=500.0, stop=495.0, target=510.0)
    trigger_id = fill["gtt_trigger_id"]
    assert trigger_id in mock_kite.gtts
    execution.cancel_backstop(trigger_id)
    assert trigger_id not in mock_kite.gtts


def test_reconcile_detects_matching_position(mock_kite):
    execution, cfg = make_execution(mock_kite)
    mock_kite.net_positions = [{"tradingsymbol": "TESTSYM", "quantity": 100}]
    assert execution.reconcile("TESTSYM", 100, "LONG") is True


def test_reconcile_detects_mismatch(mock_kite):
    execution, cfg = make_execution(mock_kite)
    mock_kite.net_positions = [{"tradingsymbol": "TESTSYM", "quantity": 70}]
    assert execution.reconcile("TESTSYM", 100, "LONG") is False


def test_force_square_off_closes_open_positions(mock_kite):
    execution, cfg = make_execution(mock_kite)
    mock_kite.net_positions = [{"tradingsymbol": "TESTSYM", "quantity": 50}]
    execution.force_square_off_all(["TESTSYM"])
    # a SELL order should have been placed to flatten the LONG 50
    assert len(mock_kite.orders) == 1
