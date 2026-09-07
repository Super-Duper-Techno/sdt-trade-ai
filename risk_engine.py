"""
SDT Trade AI — risk engine (Sections 2, 6, 27).

This module answers: "How much can we risk?" It is the only place position
size gets computed, and it is the only place that can lock the whole system
for the day. Nothing else, including the AI signal engine, can override it.
"""
import json
import math
import os
from dataclasses import dataclass, field
from datetime import date

from config import RiskConfig

STATE_FILE = "daily_state.json"


@dataclass
class DailyState:
    trading_date: str = field(default_factory=lambda: str(date.today()))
    trades_today: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    kill_switch_active: bool = False
    kill_switch_reason: str = ""

    def save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.__dict__, f)

    @classmethod
    def load(cls):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                data = json.load(f)
            if data.get("trading_date") == str(date.today()):
                return cls(**data)
        return cls()  # fresh day, fresh state


class RiskEngine:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.state = DailyState.load()

    # ---- gate checks (Section 27 hard rules) ----
    def can_trade(self) -> tuple[bool, str]:
        if self.state.kill_switch_active:
            return False, f"Kill switch active: {self.state.kill_switch_reason}"
        if self.state.trades_today >= self.cfg.max_trades_per_day:
            return False, "Max trades per day reached"
        if self.state.consecutive_losses >= self.cfg.max_consecutive_losses:
            self._trigger_kill("Max consecutive losses reached")
            return False, "Max consecutive losses reached"
        if self.state.daily_pnl <= -self.cfg.daily_loss_limit():
            self._trigger_kill("Daily loss limit reached")
            return False, "Daily loss limit reached"
        return True, "ok"

    # ---- position sizing (Section 6) ----
    def size_position(self, entry_price: float, stop_price: float) -> dict:
        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share <= 0:
            return {"qty": 0, "reason": "invalid stop distance"}

        risk_amount = self.cfg.risk_amount()
        qty = math.floor(risk_amount / risk_per_share)

        max_value_qty = math.floor(self.cfg.max_position_value() / entry_price)
        qty = min(qty, max_value_qty)

        if qty < 1:
            return {"qty": 0, "reason": "position size below 1 share after limits"}

        return {
            "qty": qty,
            "risk_per_share": risk_per_share,
            "risk_amount": round(qty * risk_per_share, 2),
            "position_value": round(qty * entry_price, 2),
        }

    # ---- risk/reward gate (Section 8) ----
    def check_risk_reward(self, entry: float, stop: float, target: float) -> bool:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk <= 0:
            return False
        return (reward / risk) >= self.cfg.min_risk_reward

    # ---- called by execution.py after every closed trade ----
    def register_trade_result(self, pnl: float):
        self.state.trades_today += 1
        self.state.daily_pnl = round(self.state.daily_pnl + pnl, 2)
        self.state.consecutive_losses = self.state.consecutive_losses + 1 if pnl < 0 else 0
        self.state.save()

        if self.state.daily_pnl <= -self.cfg.daily_loss_limit():
            self._trigger_kill("Daily loss limit reached")
        elif self.state.consecutive_losses >= self.cfg.max_consecutive_losses:
            self._trigger_kill("Max consecutive losses reached")

    def register_entry(self):
        # trades_today increments on registration of a *closed* trade above;
        # this hook exists if you want to also cap concurrent open exposure.
        pass

    def manual_kill(self, reason: str = "Manual kill switch"):
        self._trigger_kill(reason)

    def resume(self):
        self.state.kill_switch_active = False
        self.state.kill_switch_reason = ""
        self.state.save()

    def _trigger_kill(self, reason: str):
        self.state.kill_switch_active = True
        self.state.kill_switch_reason = reason
        self.state.save()
