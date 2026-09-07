"""
SDT Trade AI — position monitoring / auto-exit engine (Sections 9, 10).

Answers: "Should we exit?" Runs continuously against live ticks while a
position is open. Owns stop-loss, target, breakeven-at-1R, trailing stop,
and time-based exit.
"""
import time
from dataclasses import dataclass
from datetime import datetime

from config import RiskConfig


@dataclass
class OpenPosition:
    tradingsymbol: str
    direction: str          # "LONG" | "SHORT"
    entry: float
    stop: float
    target: float
    qty: int
    opened_at: datetime
    trail_armed: bool = False
    gtt_trigger_id: int = None


class PositionMonitor:
    def __init__(self, market_data, execution, risk_engine, cfg: RiskConfig):
        self.md = market_data
        self.execution = execution
        self.risk = risk_engine
        self.cfg = cfg

    def watch(self, pos: OpenPosition, poll_seconds: float = 1.0, on_update=None, stop_flag=None):
        """Blocks until the position is closed, then returns realized pnl.

        on_update(pos, price, r_multiple): optional callback fired each poll,
        used by the dashboard to show live unrealized P&L.
        stop_flag: optional threading.Event — if set, forces an immediate exit
        (used when the dashboard Stop button is pressed mid-trade).
        """
        dir_mult = 1 if pos.direction == "LONG" else -1

        while True:
            if stop_flag is not None and stop_flag.is_set():
                fill = self.execution.exit(pos.tradingsymbol, pos.direction, pos.qty)
                self.execution.cancel_backstop(pos.gtt_trigger_id)
                pnl = round((fill["average_price"] - pos.entry) * dir_mult * pos.qty, 2)
                self.risk.register_trade_result(pnl)
                return pnl, "manual_stop"

            price = self.md.latest_price(pos.tradingsymbol, self.cfg.exchange)
            if price is None:
                time.sleep(poll_seconds)
                continue

            if on_update:
                r_dist = abs(pos.entry - pos.stop) or 1
                on_update(pos, price, ((price - pos.entry) * dir_mult) / r_dist)

            r_distance = abs(pos.entry - pos.stop)
            r_multiple = ((price - pos.entry) * dir_mult) / r_distance if r_distance else 0

            # profit protection (Section 10)
            if r_multiple >= self.cfg.trail_activate_r and not pos.trail_armed:
                pos.stop = pos.entry
                pos.trail_armed = True
                print(f"[monitor] {pos.tradingsymbol}: stop moved to breakeven at +{r_multiple:.2f}R")

            if r_multiple >= self.cfg.trail_lock_r:
                trail_stop = round(price - dir_mult * r_distance * 0.75, 2)
                pos.stop = max(pos.stop, trail_stop) if dir_mult == 1 else min(pos.stop, trail_stop)

            hit_stop = price <= pos.stop if dir_mult == 1 else price >= pos.stop
            hit_target = price >= pos.target if dir_mult == 1 else price <= pos.target
            time_up = (datetime.now() - pos.opened_at).total_seconds() >= self.cfg.time_exit_minutes * 60

            if hit_stop or hit_target or time_up:
                reason = "target" if hit_target else "time_exit" if time_up else "stop_loss"
                fill = self.execution.exit(pos.tradingsymbol, pos.direction, pos.qty)
                # Software closed the position first — cancel the broker-side
                # GTT backstop immediately or it can fire a duplicate exit.
                self.execution.cancel_backstop(pos.gtt_trigger_id)
                pnl = round((fill["average_price"] - pos.entry) * dir_mult * pos.qty, 2)
                print(f"[monitor] {pos.tradingsymbol} closed via {reason} at {fill['average_price']} — pnl {pnl}")
                self.risk.register_trade_result(pnl)
                self.execution.reconcile(pos.tradingsymbol, 0, pos.direction)
                return pnl, reason

            time.sleep(poll_seconds)
