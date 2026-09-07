"""
SDT Trade AI — main orchestrator.

MARKET DATA -> FEATURE ENGINE -> AI SIGNAL ENGINE -> ENTRY RULE ENGINE ->
RISK ENGINE -> EXECUTION ENGINE -> BROKER -> POSITION MONITORING -> AUTO-EXIT

Run with:  python main.py

Before running: python auth.py   (once per trading day)

READ THIS FIRST:
This places REAL orders with REAL money the moment PRODUCT/quantities are
non-zero and the market is open — there is no separate "paper mode" toggle
built into Kite itself. Section 23/24 of the rulebook require you to prove
this out in the /mnt/user-data/outputs/sdt_trade_ai.jsx simulator and/or a
separate backtest first, then run this with the smallest possible capital
before trusting it further. Nothing in this codebase substitutes for that.
"""
import time
from datetime import datetime

from auth import get_kite
from config import load_config, KITE_API_KEY
from market_data import MarketData
from signal_engine import SignalEngine
from rule_engine import evaluate
from risk_engine import RiskEngine
from execution import ExecutionEngine, ExecutionError
from position_monitor import PositionMonitor, OpenPosition
from logger_store import log_trade, print_daily_report


def within_market_hours(cfg) -> bool:
    now = datetime.now().time()
    open_t = datetime.strptime(cfg.market_open_time, "%H:%M").time()
    close_t = datetime.strptime(cfg.square_off_time, "%H:%M").time()
    return open_t <= now <= close_t


def run():
    cfg = load_config()
    kite = get_kite()
    md = MarketData(kite, kite.access_token, KITE_API_KEY)
    md.start_ticker(cfg.tradingsymbols, cfg.exchange)
    md.wait_for_ticks()

    signal_engine = SignalEngine()
    risk = RiskEngine(cfg)
    execution = ExecutionEngine(kite, cfg)
    monitor = PositionMonitor(md, execution, risk, cfg)

    print(f"[main] SDT Trade AI armed. Capital ₹{cfg.capital:,.0f} | "
          f"risk/trade ₹{cfg.risk_amount():,.0f} | daily loss cap ₹{cfg.daily_loss_limit():,.0f}")

    open_position = None

    while True:
        if not within_market_hours(cfg):
            print("[main] outside trading window — forcing square-off and stopping.")
            execution.force_square_off_all(cfg.tradingsymbols)
            break

        can_trade, reason = risk.can_trade()
        if not can_trade:
            print(f"[main] halted: {reason}. Sleeping 30s.")
            time.sleep(30)
            continue

        for symbol in cfg.tradingsymbols:
            try:
                df = md.historical(symbol, cfg.exchange)
                quote = md.quote(symbol, cfg.exchange)
            except Exception as e:
                print(f"[main] data error for {symbol}: {e}")
                continue

            signal = signal_engine.score(df.rename(columns={"close": "close"}))
            decision = evaluate(signal, quote, cfg, risk)

            if not decision.approved:
                continue  # NO TRADE — this is the expected common case

            print(f"[main] APPROVED {symbol} {decision.direction} qty={decision.qty} "
                  f"entry~{decision.entry} stop={decision.stop} target={decision.target} "
                  f"confidence={decision.confidence} regime={decision.regime}")

            try:
                fill = execution.enter(symbol, decision.direction, decision.qty, decision.entry,
                                        stop=decision.stop, target=decision.target)
            except ExecutionError as e:
                print(f"[main] entry failed, no position opened: {e}")
                continue

            pos = OpenPosition(
                tradingsymbol=symbol, direction=decision.direction, entry=fill["average_price"],
                stop=decision.stop, target=decision.target, qty=decision.qty, opened_at=datetime.now(),
                gtt_trigger_id=fill.get("gtt_trigger_id"),
            )
            pnl, exit_reason = monitor.watch(pos)  # blocks until this trade closes
            log_trade({
                "tradingsymbol": symbol, "direction": pos.direction, "entry": pos.entry,
                "exit": pos.entry, "qty": pos.qty, "stop": decision.stop, "target": decision.target,
                "confidence": decision.confidence, "regime": decision.regime,
                "reason": exit_reason, "pnl": pnl,
            })
            break  # re-run the outer loop / re-check risk gates before scanning again

        time.sleep(5)

    print_daily_report()


if __name__ == "__main__":
    run()
