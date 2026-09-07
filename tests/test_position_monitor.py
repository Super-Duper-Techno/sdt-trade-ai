import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import RiskConfig
from risk_engine import RiskEngine
from position_monitor import PositionMonitor, OpenPosition


class FakeMarketData:
    """Feeds a scripted sequence of prices, one per latest_price() call."""
    def __init__(self, price_sequence):
        self._prices = list(price_sequence)
        self._i = 0

    def latest_price(self, symbol, exchange):
        price = self._prices[min(self._i, len(self._prices) - 1)]
        self._i += 1
        return price


class FakeExecution:
    def __init__(self):
        self.exit_calls = []
        self.cancel_calls = []
        self.next_fill_price = None

    def exit(self, symbol, direction, qty):
        self.exit_calls.append((symbol, direction, qty))
        return {"average_price": self.next_fill_price}

    def cancel_backstop(self, trigger_id):
        self.cancel_calls.append(trigger_id)

    def reconcile(self, symbol, qty, direction):
        return True


def make_monitor(tmp_path, prices, **cfg_overrides):
    os.chdir(tmp_path)
    defaults = dict(capital=1_000_000, max_daily_loss_pct=10.0, max_consecutive_losses=10,
                     time_exit_minutes=60, trail_activate_r=1.0, trail_lock_r=1.5)
    defaults.update(cfg_overrides)
    cfg = RiskConfig(**defaults)
    risk = RiskEngine(cfg)
    md = FakeMarketData(prices)
    execution = FakeExecution()
    monitor = PositionMonitor(md, execution, risk, cfg)
    return monitor, execution, risk


def test_long_position_hits_stop_loss(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[498, 496, 494])
    execution.next_fill_price = 494
    pos = OpenPosition("TESTSYM", "LONG", entry=500, stop=495, target=520, qty=100, opened_at=datetime.now())
    pnl, reason = monitor.watch(pos, poll_seconds=0)
    assert reason == "stop_loss"
    assert pnl < 0
    assert execution.exit_calls[0] == ("TESTSYM", "LONG", 100)


def test_long_position_hits_target(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[505, 510, 521])
    execution.next_fill_price = 520
    pos = OpenPosition("TESTSYM", "LONG", entry=500, stop=495, target=520, qty=100, opened_at=datetime.now())
    pnl, reason = monitor.watch(pos, poll_seconds=0)
    assert reason == "target"
    assert pnl > 0


def test_short_position_direction_inverted_correctly(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[499, 497, 494, 489])
    execution.next_fill_price = 489
    pos = OpenPosition("TESTSYM", "SHORT", entry=500, stop=505, target=490, qty=100, opened_at=datetime.now())
    pnl, reason = monitor.watch(pos, poll_seconds=0)
    assert reason == "target"
    assert pnl > 0  # price fell, short position profits


def test_breakeven_stop_moves_after_1r(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[505, 500.5, 499])
    # entry 500, stop 495 -> risk=5. At 505 that's +1R -> stop should move to breakeven (500).
    # price then dips to 499, which is BELOW the new breakeven stop of 500 -> should exit there.
    execution.next_fill_price = 500
    pos = OpenPosition("TESTSYM", "LONG", entry=500, stop=495, target=520, qty=100, opened_at=datetime.now())
    pnl, reason = monitor.watch(pos, poll_seconds=0)
    assert reason == "stop_loss"
    assert pnl == 0  # exited flat at breakeven, not at a loss, thanks to profit protection


def test_time_based_exit_after_max_hold(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[501], time_exit_minutes=0)
    execution.next_fill_price = 501
    stale_open_time = datetime.now() - timedelta(minutes=5)
    pos = OpenPosition("TESTSYM", "LONG", entry=500, stop=495, target=520, qty=100, opened_at=stale_open_time)
    pnl, reason = monitor.watch(pos, poll_seconds=0)
    assert reason == "time_exit"


def test_gtt_backstop_cancelled_on_software_exit(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[494])
    execution.next_fill_price = 494
    pos = OpenPosition("TESTSYM", "LONG", entry=500, stop=495, target=520, qty=100,
                        opened_at=datetime.now(), gtt_trigger_id=42)
    monitor.watch(pos, poll_seconds=0)
    assert execution.cancel_calls == [42]


def test_trade_result_registered_with_risk_engine(tmp_path):
    monitor, execution, risk = make_monitor(tmp_path, prices=[510], time_exit_minutes=0)
    execution.next_fill_price = 510
    stale_open_time = datetime.now() - timedelta(minutes=5)
    pos = OpenPosition("TESTSYM", "LONG", entry=500, stop=495, target=520, qty=100, opened_at=stale_open_time)
    monitor.watch(pos, poll_seconds=0)
    assert risk.state.trades_today == 1
    assert risk.state.daily_pnl == 1000  # (510-500)*100
