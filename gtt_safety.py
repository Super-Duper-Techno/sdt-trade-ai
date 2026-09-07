"""
SDT Trade AI — GTT (Good Till Triggered) safety net.

position_monitor.py enforces stop/target by watching live ticks and firing
market orders — but that only works while the Python process is alive. If
it crashes, gets killed, or loses its network connection with a position
open, that position is naked until someone notices.

This module places a broker-side two-leg OCO GTT immediately after entry
as a backstop: even if the process dies, Kite itself will exit the
position at the stop or target. When the software exits the position
normally, the GTT is cancelled so it doesn't fire a second time.

Reference: https://kite.trade/docs/connect/v3/gtt/
Verify field names against current Kite docs before relying on this —
broker API surfaces do change.
"""


def place_protective_gtt(kite, tradingsymbol: str, exchange: str, direction: str,
                          qty: int, entry: float, stop: float, target: float) -> int:
    """Places a two-leg OCO GTT: exits via stop OR target, whichever hits first."""
    exit_txn = kite.TRANSACTION_TYPE_SELL if direction == "LONG" else kite.TRANSACTION_TYPE_BUY

    # Kite requires trigger_values sorted ascending regardless of direction.
    trigger_values = sorted([stop, target])

    orders = [
        {
            "transaction_type": exit_txn,
            "quantity": qty,
            "order_type": kite.ORDER_TYPE_LIMIT,
            "product": kite.PRODUCT_MIS,
            "price": leg_price,
        }
        for leg_price in (stop, target)
    ]

    result = kite.place_gtt(
        trigger_type=kite.GTT_TYPE_OCO,
        tradingsymbol=tradingsymbol,
        exchange=exchange,
        trigger_values=trigger_values,
        last_price=entry,
        orders=orders,
    )
    return result["trigger_id"]


def cancel_protective_gtt(kite, trigger_id: int):
    """Call this the instant the software exits a position normally —
    otherwise the GTT is still live and can fire a duplicate exit order."""
    if trigger_id is None:
        return
    try:
        kite.delete_gtt(trigger_id)
    except Exception as e:
        print(f"[gtt_safety] WARNING: failed to cancel GTT {trigger_id} — check manually: {e}")
