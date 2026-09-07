import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import RiskConfig
from risk_engine import RiskEngine
from rule_engine import evaluate


def make_risk(tmp_path, **overrides):
    os.chdir(tmp_path)
    defaults = dict(capital=1_000_000, risk_per_trade_pct=0.5, max_daily_loss_pct=2.0,
                     min_ai_confidence=70, min_risk_reward=2.0, max_spread_pct=0.15)
    defaults.update(overrides)
    cfg = RiskConfig(**defaults)
    return cfg, RiskEngine(cfg)


def good_signal(score=85, direction="LONG", regime="TRENDING_UP"):
    return {
        "score": score, "direction": direction, "regime": regime,
        "features": {"valid": True, "last_price": 500.0, "atr_proxy": 2.0, "slope": 0.5, "momentum": 0.3, "vol_ratio": 1.0},
    }


def good_quote(spread_pct=0.05):
    return {"ltp": 500.0, "bid": 499.9, "ask": 500.1, "spread_pct": spread_pct, "volume": 100000}


def test_approves_valid_setup(tmp_path):
    cfg, risk = make_risk(tmp_path)
    decision = evaluate(good_signal(), good_quote(), cfg, risk)
    assert decision.approved is True
    assert decision.direction == "LONG"
    assert decision.qty > 0


def test_rejects_when_kill_switch_active(tmp_path):
    cfg, risk = make_risk(tmp_path)
    risk.manual_kill("test")
    decision = evaluate(good_signal(), good_quote(), cfg, risk)
    assert decision.approved is False
    assert "kill switch" in decision.reason.lower()


def test_rejects_low_confidence(tmp_path):
    cfg, risk = make_risk(tmp_path)
    decision = evaluate(good_signal(score=50), good_quote(), cfg, risk)
    assert decision.approved is False
    assert "confidence" in decision.reason


def test_rejects_ranging_regime_no_strategy(tmp_path):
    cfg, risk = make_risk(tmp_path)
    signal = good_signal(direction=None, regime="RANGING")
    decision = evaluate(signal, good_quote(), cfg, risk)
    assert decision.approved is False
    assert "regime_supported" in decision.reason


def test_rejects_wide_spread(tmp_path):
    cfg, risk = make_risk(tmp_path)
    decision = evaluate(good_signal(), good_quote(spread_pct=1.0), cfg, risk)
    assert decision.approved is False
    assert "spread" in decision.reason


def test_rejects_invalid_market_data(tmp_path):
    cfg, risk = make_risk(tmp_path)
    signal = {"score": 90, "direction": "LONG", "regime": "ABNORMAL", "features": {"valid": False}}
    decision = evaluate(signal, good_quote(), cfg, risk)
    assert decision.approved is False
    assert "market_data_valid" in decision.reason


def test_rejects_when_daily_loss_limit_already_hit(tmp_path):
    cfg, risk = make_risk(tmp_path)
    risk.register_trade_result(-25000)  # exceeds 2% of 1,000,000 = 20,000
    decision = evaluate(good_signal(), good_quote(), cfg, risk)
    assert decision.approved is False


def test_short_direction_produces_stop_above_entry(tmp_path):
    cfg, risk = make_risk(tmp_path)
    decision = evaluate(good_signal(direction="SHORT", regime="TRENDING_DOWN"), good_quote(), cfg, risk)
    assert decision.approved is True
    assert decision.stop > decision.entry
    assert decision.target < decision.entry


def test_long_direction_produces_stop_below_entry(tmp_path):
    cfg, risk = make_risk(tmp_path)
    decision = evaluate(good_signal(), good_quote(), cfg, risk)
    assert decision.approved is True
    assert decision.stop < decision.entry
    assert decision.target > decision.entry


def test_risk_reward_is_always_at_least_minimum(tmp_path):
    cfg, risk = make_risk(tmp_path, min_risk_reward=3.0)
    decision = evaluate(good_signal(), good_quote(), cfg, risk)
    assert decision.approved is True
    risk_amt = abs(decision.entry - decision.stop)
    reward_amt = abs(decision.target - decision.entry)
    assert reward_amt / risk_amt >= 3.0 - 1e-9
