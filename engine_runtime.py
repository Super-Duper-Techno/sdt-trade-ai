"""
SDT Trade AI — engine runtime for the dashboard.

Wraps the same pipeline as main.py (market data -> signal -> rule engine ->
risk engine -> execution -> monitor) but runs it in a background thread and
publishes a thread-safe state snapshot for app.py to serve to the browser,
instead of blocking a terminal.
"""
import threading
import time
from dataclasses import asdict
from datetime import datetime

from config import load_config, KITE_API_KEY
from auth import new_kite_client, complete_login, try_cached_session, get_login_url
from market_data import MarketData
from signal_engine import SignalEngine
from rule_engine import evaluate, STEP_ORDER
from risk_engine import RiskEngine
from execution import ExecutionEngine, ExecutionError
from paper_execution import PaperExecutionEngine
from position_monitor import PositionMonitor, OpenPosition
from logger_store import log_trade, daily_report


def within_market_hours(cfg) -> bool:
    now = datetime.now().time()
    open_t = datetime.strptime(cfg.market_open_time, "%H:%M").time()
    close_t = datetime.strptime(cfg.square_off_time, "%H:%M").time()
    return open_t <= now <= close_t


class EngineRuntime:
    def __init__(self):
        self.lock = threading.Lock()
        self.cfg = load_config()
        self.kite = try_cached_session()
        self.risk = RiskEngine(self.cfg)
        self.paper_mode = True
        self.thread = None
        self.stop_flag = threading.Event()
        self.md = None
        self.execution = None
        self.monitor = None
        self.signal_engine = SignalEngine()

        self.state = {
            "connected": self.kite is not None,
            "status": "stopped",       # stopped | connecting | scanning | in_position | halted | error
            "message": "",
            "paper_mode": self.paper_mode,
            "config": self._public_config(),
            "prices": {},
            "regime": {},
            "last_signal": None,
            "waterfall": [{"label": s, "state": "idle"} for s in STEP_ORDER],
            "position": None,
            "daily_pnl": 0,
            "trades_today": 0,
            "consecutive_losses": 0,
            "kill_switch": {"active": False, "reason": None},
            "trade_log": [],
        }
        self._sync_risk_state()

    # ---------------- public config / snapshot ----------------
    def _public_config(self):
        c = self.cfg
        return {
            "capital": c.capital, "risk_per_trade_pct": c.risk_per_trade_pct,
            "max_daily_loss_pct": c.max_daily_loss_pct, "max_consecutive_losses": c.max_consecutive_losses,
            "max_trades_per_day": c.max_trades_per_day, "min_ai_confidence": c.min_ai_confidence,
            "min_risk_reward": c.min_risk_reward, "tradingsymbols": list(c.tradingsymbols),
            "exchange": c.exchange,
        }

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update_config(self, **kwargs):
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Stop the engine before changing configuration.")
        from dataclasses import replace
        if "tradingsymbols" in kwargs:
            kwargs["tradingsymbols"] = tuple(kwargs["tradingsymbols"])
        self.cfg = replace(self.cfg, **kwargs)
        self.risk = RiskEngine(self.cfg)
        with self.lock:
            self.state["config"] = self._public_config()
        self._sync_risk_state()

    def set_paper_mode(self, enabled: bool):
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Stop the engine before switching paper/live mode.")
        self.paper_mode = enabled
        with self.lock:
            self.state["paper_mode"] = enabled

    # ---------------- auth ----------------
    def login_url(self):
        return get_login_url()

    def connect(self, request_token: str):
        self.kite = complete_login(request_token)
        with self.lock:
            self.state["connected"] = True

    # ---------------- lifecycle ----------------
    def start(self):
        if self.kite is None:
            raise RuntimeError("Not connected to Kite yet.")
        if self.thread and self.thread.is_alive():
            return
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    def manual_kill(self):
        self.risk.manual_kill("Manual kill switch (dashboard)")
        self._sync_risk_state()

    def resume(self):
        self.risk.resume()
        self._sync_risk_state()

    def reset_day(self):
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Stop the engine before resetting the day.")
        self.risk.state.trades_today = 0
        self.risk.state.consecutive_losses = 0
        self.risk.state.daily_pnl = 0
        self.risk.state.kill_switch_active = False
        self.risk.state.kill_switch_reason = ""
        self.risk.state.save()
        self._sync_risk_state()

    # ---------------- internals ----------------
    def _sync_risk_state(self):
        with self.lock:
            self.state["daily_pnl"] = self.risk.state.daily_pnl
            self.state["trades_today"] = self.risk.state.trades_today
            self.state["consecutive_losses"] = self.risk.state.consecutive_losses
            self.state["kill_switch"] = {
                "active": self.risk.state.kill_switch_active,
                "reason": self.risk.state.kill_switch_reason,
            }

    def _set_status(self, status, message=""):
        with self.lock:
            self.state["status"] = status
            self.state["message"] = message

    def _mark_waterfall(self, failed_step_label: str):
        with self.lock:
            steps = self.state["waterfall"]
            failed_idx = next((i for i, s in enumerate(steps) if s["label"] == failed_step_label), len(steps))
            for i, s in enumerate(steps):
                s["state"] = "pass" if i < failed_idx else "fail" if i == failed_idx else "idle"

    def _mark_all_pass(self):
        with self.lock:
            for s in self.state["waterfall"]:
                s["state"] = "pass"

    def _position_update_cb(self, pos, price, r_multiple):
        with self.lock:
            self.state["position"] = {
                "tradingsymbol": pos.tradingsymbol, "direction": pos.direction, "entry": pos.entry,
                "stop": pos.stop, "target": pos.target, "qty": pos.qty,
                "current_price": price, "r_multiple": round(r_multiple, 2),
                "unrealized": round((price - pos.entry) * (1 if pos.direction == "LONG" else -1) * pos.qty, 2),
            }

    def _run_loop(self):
        try:
            self._set_status("connecting")
            self.md = MarketData(self.kite, self.kite.access_token, KITE_API_KEY)
            self.md.start_ticker(self.cfg.tradingsymbols, self.cfg.exchange)
            self.md.wait_for_ticks()

            self.execution = (
                PaperExecutionEngine(self.kite, self.cfg, self.md) if self.paper_mode
                else ExecutionEngine(self.kite, self.cfg)
            )
            self.monitor = PositionMonitor(self.md, self.execution, self.risk, self.cfg)
            self._set_status("scanning")

            while not self.stop_flag.is_set():
                if not within_market_hours(self.cfg):
                    self.execution.force_square_off_all(self.cfg.tradingsymbols)
                    self._set_status("stopped", "Outside trading window — auto square-off complete.")
                    return

                can_trade, reason = self.risk.can_trade()
                self._sync_risk_state()
                if not can_trade:
                    self._set_status("halted", reason)
                    time.sleep(2)
                    continue

                self._set_status("scanning")
                traded_this_pass = False

                for symbol in self.cfg.tradingsymbols:
                    if self.stop_flag.is_set():
                        break
                    try:
                        df = self.md.historical(symbol, self.cfg.exchange)
                        quote = self.md.quote(symbol, self.cfg.exchange)
                    except Exception as e:
                        with self.lock:
                            self.state["message"] = f"data error for {symbol}: {e}"
                        continue

                    with self.lock:
                        self.state["prices"][symbol] = quote["ltp"]

                    signal = self.signal_engine.score(df.rename(columns={"close": "close"}))
                    with self.lock:
                        self.state["last_signal"] = {
                            "symbol": symbol, "score": signal["score"],
                            "direction": signal["direction"], "regime": signal["regime"],
                        }
                        self.state["regime"][symbol] = signal["regime"]

                    decision = evaluate(signal, quote, self.cfg, self.risk)
                    failed_label = decision.reason.split(":")[0] if not decision.approved else None
                    if failed_label and any(s["label"] == failed_label for s in self.state["waterfall"]):
                        self._mark_waterfall(failed_label)
                    if not decision.approved:
                        continue

                    self._mark_all_pass()
                    try:
                        fill = self.execution.enter(symbol, decision.direction, decision.qty, decision.entry,
                                                     stop=decision.stop, target=decision.target)
                    except ExecutionError as e:
                        with self.lock:
                            self.state["message"] = f"entry failed: {e}"
                        continue

                    pos = OpenPosition(
                        tradingsymbol=symbol, direction=decision.direction, entry=fill["average_price"],
                        stop=decision.stop, target=decision.target, qty=decision.qty, opened_at=datetime.now(),
                        gtt_trigger_id=fill.get("gtt_trigger_id"),
                    )
                    self._set_status("in_position", f"{symbol} {decision.direction}")
                    pnl, exit_reason = self.monitor.watch(
                        pos, poll_seconds=1.0, on_update=self._position_update_cb, stop_flag=self.stop_flag,
                    )
                    log_trade({
                        "tradingsymbol": symbol, "direction": pos.direction, "entry": pos.entry,
                        "exit": pos.entry, "qty": pos.qty, "stop": decision.stop, "target": decision.target,
                        "confidence": decision.confidence, "regime": decision.regime,
                        "reason": exit_reason, "pnl": pnl,
                    })
                    with self.lock:
                        self.state["position"] = None
                        self.state["trade_log"].insert(0, {
                            "symbol": symbol, "direction": pos.direction, "entry": pos.entry,
                            "exit": fill["average_price"], "qty": pos.qty, "reason": exit_reason, "pnl": pnl,
                        })
                        self.state["trade_log"] = self.state["trade_log"][:50]
                    self._sync_risk_state()
                    traded_this_pass = True
                    break  # re-check risk gates before scanning again

                time.sleep(1 if traded_this_pass else 3)

            self._set_status("stopped", "Stopped by user.")
        except Exception as e:
            self._set_status("error", str(e))
            raise

    def report(self):
        return daily_report()


runtime = EngineRuntime()
