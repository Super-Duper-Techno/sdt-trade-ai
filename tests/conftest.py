"""
Shared test fixtures. MockKite stands in for kiteconnect.KiteConnect so the
whole pipeline can be exercised — order placement, fills, positions,
quotes, GTT — without a network call or a live account.
"""
import itertools
import pytest


class MockKite:
    # constants mirrored from the real KiteConnect class
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"
    VARIETY_REGULAR = "regular"
    ORDER_TYPE_MARKET = "MARKET"
    ORDER_TYPE_LIMIT = "LIMIT"
    ORDER_TYPE_SL = "SL"
    PRODUCT_MIS = "MIS"
    GTT_TYPE_OCO = "two-leg"

    def __init__(self):
        self._order_ids = itertools.count(1)
        self.orders = {}          # order_id -> status history
        self.gtts = {}            # trigger_id -> gtt dict
        self._gtt_ids = itertools.count(1)
        self.net_positions = []
        self.quotes = {}
        self.historical = {}
        self.access_token = "mock-token"
        # script controls how the next order resolves, for test scenarios
        self.next_order_status = "COMPLETE"
        self.next_fill_price = None

    # ---- orders ----
    def place_order(self, **kwargs):
        order_id = str(next(self._order_ids))
        fill_price = self.next_fill_price or kwargs.get("_test_price", 100.0)
        self.orders[order_id] = [{
            "status": self.next_order_status,
            "average_price": fill_price,
            "filled_quantity": kwargs["quantity"] if self.next_order_status == "COMPLETE" else 0,
            "status_message": None,
        }]
        return order_id

    def order_history(self, order_id):
        return self.orders[order_id]

    def positions(self):
        return {"net": self.net_positions}

    def quote(self, keys):
        return {k: self.quotes[k] for k in keys}

    def historical_data(self, token, from_dt, to_dt, interval):
        return self.historical.get(token, [])

    def instruments(self, exchange):
        return [{"tradingsymbol": "TESTSYM", "instrument_token": 12345, "exchange": exchange}]

    def profile(self):
        return {"user_name": "Test User", "user_id": "T1"}

    # ---- GTT ----
    def place_gtt(self, **kwargs):
        trigger_id = next(self._gtt_ids)
        self.gtts[trigger_id] = kwargs
        return {"trigger_id": trigger_id}

    def delete_gtt(self, trigger_id):
        self.gtts.pop(trigger_id, None)
        return {"trigger_id": trigger_id}

    def get_gtts(self):
        return list(self.gtts.values())


@pytest.fixture
def mock_kite():
    return MockKite()
