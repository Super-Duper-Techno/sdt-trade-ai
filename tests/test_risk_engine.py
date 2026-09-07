import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import RiskConfig
from risk_engine import RiskEngine, STATE_FILE


def fresh_engine(tmp_path, **overrides):
    os.chdir(tmp_path)
    defaults = dict(capital=1_000_000, risk_per_trade_pct=0.5, max_daily_loss_pct=2.0,
                     max_consecutive_losses=3, max_trades_per_day=4)
    defaults.update(overrides)
    return RiskEngine(RiskConfig(**defaults))


def test_position_sizing_matches_manual_formula(tmp_path):
    risk = fresh_engine(tmp_path)
    # capital=1,000,000 * 0.5% = 5,000 risk. entry=500, stop=495 -> risk/share=5 -> qty=1000
    sizing = risk.size_position(entry_price=500, stop_price=495)
    assert sizing["qty"] == 1000
    assert sizing["risk_amount"] == 5000


def test_position_size_capped_by_max_position_value(tmp_path):
    risk = fresh_engine(tmp_path, max_position_value_pct=1.0)  # cap = 10,000
    sizing = risk.size_position(entry_price=500, stop_price=495)
    # 1000 shares * 500 = 500,000 normally, but value cap forces qty down to 20
    assert sizing["qty"] == 20


def test_zero_stop_distance_rejected(tmp_path):
    risk = fresh_engine(tmp_path)
    sizing = risk.size_position(entry_price=500, stop_price=500)
    assert sizing["qty"] == 0


def test_daily_loss_limit_triggers_kill_switch(tmp_path):
    risk = fresh_engine(tmp_path)  # daily loss limit = 1,000,000 * 2% = 20,000
    risk.register_trade_result(-12000)
    can_trade, _ = risk.can_trade()
    assert can_trade is True
    risk.register_trade_result(-9000)  # total -21,000, breaches limit
    can_trade, reason = risk.can_trade()
    assert can_trade is False
    assert "daily loss" in reason.lower() or risk.state.kill_switch_active


def test_consecutive_losses_trigger_kill_switch(tmp_path):
    risk = fresh_engine(tmp_path)
    risk.register_trade_result(-100)
    risk.register_trade_result(-100)
    assert risk.can_trade()[0] is True
    risk.register_trade_result(-100)  # 3rd consecutive loss
    can_trade, reason = risk.can_trade()
    assert can_trade is False
    assert risk.state.consecutive_losses == 3


def test_winning_trade_resets_consecutive_losses(tmp_path):
    risk = fresh_engine(tmp_path)
    risk.register_trade_result(-100)
    risk.register_trade_result(-100)
    risk.register_trade_result(500)  # win resets streak
    assert risk.state.consecutive_losses == 0
    assert risk.can_trade()[0] is True


def test_max_trades_per_day_blocks_further_entries(tmp_path):
    risk = fresh_engine(tmp_path, max_trades_per_day=2)
    risk.register_trade_result(10)
    risk.register_trade_result(10)
    can_trade, reason = risk.can_trade()
    assert can_trade is False
    assert "max trades" in reason.lower()


def test_manual_kill_switch_blocks_and_resume_unblocks(tmp_path):
    risk = fresh_engine(tmp_path)
    risk.manual_kill("test halt")
    assert risk.can_trade()[0] is False
    risk.resume()
    assert risk.can_trade()[0] is True


def test_martingale_flag_cannot_be_enabled(tmp_path):
    import pytest
    from config import load_config
    cfg_path = os.path.join(tmp_path, "martingale_config.json")
    with open(cfg_path, "w") as f:
        f.write('{"allow_martingale": true}')
    with pytest.raises(AssertionError):
        load_config(cfg_path)
