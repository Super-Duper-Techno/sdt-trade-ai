"""
SDT Trade AI — deterministic rule engine (Sections 3, 13, 28).

Answers: "Is this setup allowed?" Every condition must pass. The AI signal
is just one input among many here — it cannot skip any other check.
"""
from dataclasses import dataclass
from typing import Optional

from config import RiskConfig
from risk_engine import RiskEngine


@dataclass
class TradeDecision:
    approved: bool
    reason: str
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    qty: Optional[int] = None
    confidence: Optional[int] = None
    regime: Optional[str] = None


STEP_ORDER = [
    "market_data_valid",
    "liquidity_spread",
    "regime_supported",
    "signal_generated",
    "confidence_threshold",
    "stop_loss_calculable",
    "risk_reward",
    "position_size",
    "daily_risk_available",
]


def evaluate(signal: dict, quote: dict, cfg: RiskConfig, risk: RiskEngine) -> TradeDecision:
    """Runs the full waterfall. Returns on the first failed condition — NO TRADE."""

    can_trade, reason = risk.can_trade()
    if not can_trade:
        return TradeDecision(approved=False, reason=reason)

    if not signal.get("features", {}).get("valid"):
        return TradeDecision(approved=False, reason="market_data_valid: insufficient/invalid data")

    if quote["spread_pct"] > cfg.max_spread_pct:
        return TradeDecision(approved=False, reason=f"liquidity_spread: {quote['spread_pct']}% > {cfg.max_spread_pct}%")

    if signal["direction"] is None:
        return TradeDecision(approved=False, reason=f"regime_supported: {signal['regime']} has no active strategy")

    if signal["score"] < cfg.min_ai_confidence:
        return TradeDecision(approved=False, reason=f"confidence_threshold: {signal['score']} < {cfg.min_ai_confidence}")

    entry = quote["ltp"]
    atr = signal["features"]["atr_proxy"]
    direction = signal["direction"]
    dir_mult = 1 if direction == "LONG" else -1

    stop = round(entry - dir_mult * atr * 1.5, 2)
    if abs(entry - stop) <= 0:
        return TradeDecision(approved=False, reason="stop_loss_calculable: zero risk distance")

    target = round(entry + dir_mult * atr * 1.5 * cfg.min_risk_reward, 2)
    if not risk.check_risk_reward(entry, stop, target):
        return TradeDecision(approved=False, reason="risk_reward: below minimum")

    sizing = risk.size_position(entry, stop)
    if sizing["qty"] < 1:
        return TradeDecision(approved=False, reason=f"position_size: {sizing['reason']}")

    # daily_risk_available already covered by risk.can_trade() above,
    # re-checked here in case sizing math pushed exposure over the line.
    if risk.state.daily_pnl <= -cfg.daily_loss_limit():
        return TradeDecision(approved=False, reason="daily_risk_available: limit reached")

    return TradeDecision(
        approved=True, reason="all conditions passed",
        direction=direction, entry=entry, stop=stop, target=target,
        qty=sizing["qty"], confidence=signal["score"], regime=signal["regime"],
    )
