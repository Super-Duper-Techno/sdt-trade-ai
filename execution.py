"""
SDT Trade AI — execution engine (Sections 14, 15).

Answers: "Can we safely execute it?" Never assumes an order filled — always
confirms status against the broker, and reconciles internal vs broker
positions before trusting internal state.
"""
import time

from config import RiskConfig
from gtt_safety import place_protective_gtt, cancel_protective_gtt


class ExecutionError(Exception):
    pass


def _with_retries(fn, retries=3, base_delay=1.0, retry_exceptions=(Exception,)):
    """Retries a broker call with exponential backoff. Order placement itself
    is NOT retried blindly (a duplicate order is worse than a failed one) —
    this is for read/status calls where retrying is safe. See Section 14."""
    last_err = None
    for attempt in range(retries):
        try:
            return fn()
        except retry_exceptions as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_err


class ExecutionEngine:
    def __init__(self, kite, cfg: RiskConfig):
        self.kite = kite
        self.cfg = cfg

    def enter(self, tradingsymbol: str, direction: str, qty: int, expected_price: float,
              stop: float = None, target: float = None) -> dict:
        txn = self.kite.TRANSACTION_TYPE_BUY if direction == "LONG" else self.kite.TRANSACTION_TYPE_SELL
        # Entry order placement is deliberately NOT retried — if the broker
        # accepted it but the response was lost, retrying would double the
        # position. A failed placement raises and no trade is registered.
        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.cfg.exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=txn,
            quantity=qty,
            order_type=self.kite.ORDER_TYPE_MARKET,
            product=self.cfg.product,
        )
        fill = self._confirm_fill(order_id)
        slippage_pct = abs(fill["average_price"] - expected_price) / expected_price * 100
        if slippage_pct > self.cfg.max_slippage_pct:
            print(f"[execution] WARNING slippage {slippage_pct:.3f}% exceeds {self.cfg.max_slippage_pct}% on entry")

        fill["gtt_trigger_id"] = None
        if stop is not None and target is not None:
            try:
                fill["gtt_trigger_id"] = place_protective_gtt(
                    self.kite, tradingsymbol, self.cfg.exchange, direction, qty,
                    fill["average_price"], stop, target,
                )
            except Exception as e:
                # A missing GTT backstop is a real risk but NOT a reason to
                # unwind a filled position — surface it loudly instead.
                print(f"[execution] WARNING: protective GTT failed to place: {e}. "
                      f"Position is live with NO broker-side backstop — monitor closely.")
        return fill

    def cancel_backstop(self, trigger_id):
        cancel_protective_gtt(self.kite, trigger_id)

    def exit(self, tradingsymbol: str, direction: str, qty: int) -> dict:
        # exiting a LONG means SELL, exiting a SHORT means BUY
        txn = self.kite.TRANSACTION_TYPE_SELL if direction == "LONG" else self.kite.TRANSACTION_TYPE_BUY
        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.cfg.exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=txn,
            quantity=qty,
            order_type=self.kite.ORDER_TYPE_MARKET,
            product=self.cfg.product,
        )
        return self._confirm_fill(order_id)

    def _confirm_fill(self, order_id: str, timeout: int = 15) -> dict:
        """Never assume a fill — poll broker order status until COMPLETE or timeout.
        Status polling itself IS retried (Section 14) — a transient network
        blip here shouldn't be mistaken for order failure."""
        start = time.time()
        while time.time() - start < timeout:
            history = _with_retries(lambda: self.kite.order_history(order_id), retries=3, base_delay=0.5)
            latest = history[-1]
            status = latest["status"]
            if status == "COMPLETE":
                return {
                    "order_id": order_id,
                    "average_price": latest["average_price"],
                    "filled_quantity": latest["filled_quantity"],
                    "status": status,
                }
            if status in ("REJECTED", "CANCELLED"):
                raise ExecutionError(f"Order {order_id} failed: {status} — {latest.get('status_message')}")
            time.sleep(1)
        raise ExecutionError(f"Order {order_id} status unknown after {timeout}s — treat as unconfirmed, do not assume fill")

    def reconcile(self, tradingsymbol: str, expected_qty: int, expected_direction: str) -> bool:
        """Compares internal expected position against the broker's actual position (Section 15)."""
        positions = self.kite.positions()["net"]
        match = next((p for p in positions if p["tradingsymbol"] == tradingsymbol), None)
        broker_qty = match["quantity"] if match else 0
        expected_signed = expected_qty if expected_direction == "LONG" else -expected_qty
        if broker_qty != expected_signed:
            print(f"[execution] POSITION MISMATCH: internal={expected_signed} broker={broker_qty}")
            return False
        return True

    def force_square_off_all(self, tradingsymbols):
        """Section 9F / 17 — close everything before market cutoff, no overnight positions."""
        positions = self.kite.positions()["net"]
        for p in positions:
            if p["tradingsymbol"] in tradingsymbols and p["quantity"] != 0:
                direction = "LONG" if p["quantity"] > 0 else "SHORT"
                qty = abs(p["quantity"])
                print(f"[execution] forced square-off: {p['tradingsymbol']} {direction} {qty}")
                self.exit(p["tradingsymbol"], direction, qty)
