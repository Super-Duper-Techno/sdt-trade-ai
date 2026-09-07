"""
SDT Trade AI — paper execution engine.

Same method signatures as execution.py's ExecutionEngine, so rule_engine,
position_monitor, and main/engine_runtime don't need to know which one
they're talking to. Uses REAL Kite market data (quotes) for realistic
fills, but places NO real orders and touches NO real money.

This is what the dashboard defaults to. Section 23 of the rulebook is
explicit: paper trading must use the same logic as the live system, not a
simplified stand-in — that's exactly what this is.
"""
import itertools


class PaperExecutionEngine:
    def __init__(self, kite, cfg, market_data):
        self.kite = kite          # used only for reference/quote calls elsewhere
        self.cfg = cfg
        self.md = market_data
        self._order_ids = itertools.count(1)
        self.paper_positions = {}  # tradingsymbol -> {direction, qty}

    def enter(self, tradingsymbol: str, direction: str, qty: int, expected_price: float,
              stop: float = None, target: float = None) -> dict:
        fill_price = self.md.latest_price(tradingsymbol, self.cfg.exchange) or expected_price
        order_id = f"PAPER-{next(self._order_ids)}"
        self.paper_positions[tradingsymbol] = {"direction": direction, "qty": qty}
        print(f"[paper] ENTER {tradingsymbol} {direction} qty={qty} @ {fill_price} (simulated)")
        return {
            "order_id": order_id, "average_price": fill_price,
            "filled_quantity": qty, "status": "COMPLETE", "gtt_trigger_id": None,
        }

    def exit(self, tradingsymbol: str, direction: str, qty: int) -> dict:
        fill_price = self.md.latest_price(tradingsymbol, self.cfg.exchange)
        self.paper_positions.pop(tradingsymbol, None)
        print(f"[paper] EXIT {tradingsymbol} {direction} qty={qty} @ {fill_price} (simulated)")
        return {"average_price": fill_price}

    def cancel_backstop(self, trigger_id):
        pass  # no real GTT was ever placed in paper mode

    def reconcile(self, tradingsymbol: str, expected_qty: int, expected_direction: str) -> bool:
        return True  # nothing to reconcile against a real broker in paper mode

    def force_square_off_all(self, tradingsymbols):
        for symbol in list(self.paper_positions):
            if symbol in tradingsymbols:
                pos = self.paper_positions.pop(symbol)
                print(f"[paper] forced square-off: {symbol} {pos['direction']} {pos['qty']} (simulated)")
