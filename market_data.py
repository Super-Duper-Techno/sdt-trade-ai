"""
SDT Trade AI — market data layer.

Wraps Kite historical candles + REST quotes for the feature engine, and
KiteTicker for the live tick stream the position monitor runs on.
"""
import threading
import time
from datetime import datetime, timedelta

import pandas as pd
from kiteconnect import KiteTicker


class MarketData:
    def __init__(self, kite, access_token, api_key):
        self.kite = kite
        self._instrument_cache = {}
        self.ticks = {}  # instrument_token -> latest tick dict
        self._ticker = KiteTicker(api_key, access_token)
        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_connect = self._on_connect
        self._ticker.on_close = self._on_close
        self._ticker.on_error = self._on_error
        self._ticker.on_reconnect = self._on_reconnect
        self._ticker.on_noreconnect = self._on_noreconnect
        self._subscribed_tokens = []
        self._lock = threading.Lock()
        self._last_tick_at = {}  # instrument_token -> monotonic timestamp, for staleness checks

    # ---- instrument resolution ----
    def instrument_token(self, tradingsymbol: str, exchange: str = "NSE") -> int:
        key = f"{exchange}:{tradingsymbol}"
        if key not in self._instrument_cache:
            if not hasattr(self, "_instruments_df"):
                self._instruments_df = pd.DataFrame(self.kite.instruments(exchange))
            row = self._instruments_df[self._instruments_df.tradingsymbol == tradingsymbol]
            if row.empty:
                raise ValueError(f"Instrument not found: {key}")
            self._instrument_cache[key] = int(row.iloc[0].instrument_token)
        return self._instrument_cache[key]

    # ---- historical candles for feature engineering ----
    def historical(self, tradingsymbol: str, exchange: str = "NSE",
                   interval: str = "minute", lookback_minutes: int = 60) -> pd.DataFrame:
        token = self.instrument_token(tradingsymbol, exchange)
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(minutes=lookback_minutes * 3)  # buffer for non-trading gaps
        candles = self.kite.historical_data(token, from_dt, to_dt, interval)
        df = pd.DataFrame(candles)
        return df.tail(lookback_minutes)

    # ---- live quote (used for spread/liquidity checks before entry) ----
    def quote(self, tradingsymbol: str, exchange: str = "NSE") -> dict:
        key = f"{exchange}:{tradingsymbol}"
        q = self.kite.quote([key])[key]
        depth = q.get("depth", {})
        best_bid = depth.get("buy", [{}])[0].get("price", q["last_price"])
        best_ask = depth.get("sell", [{}])[0].get("price", q["last_price"])
        return {
            "ltp": q["last_price"],
            "bid": best_bid,
            "ask": best_ask,
            "spread_pct": round(((best_ask - best_bid) / q["last_price"]) * 100, 4) if q["last_price"] else 999,
            "volume": q.get("volume", 0),
        }

    # ---- live ticker ----
    def start_ticker(self, tradingsymbols, exchange="NSE"):
        tokens = [self.instrument_token(s, exchange) for s in tradingsymbols]
        self._subscribed_tokens = tokens
        # KiteTicker retries its own websocket reconnect internally; these
        # bump the defaults so a brief network blip doesn't give up too fast.
        self._ticker.connect(threaded=True, reconnect_max_tries=50, reconnect_max_delay=30)

    def is_stale(self, tradingsymbol: str, exchange: str = "NSE", max_age_seconds: float = 10.0) -> bool:
        """True if we haven't received a tick for this instrument recently.
        Section 11: 'market data is delayed' is an explicit NO-TRADE condition —
        callers should check this before evaluating a signal."""
        token = self.instrument_token(tradingsymbol, exchange)
        last = self._last_tick_at.get(token)
        if last is None:
            return True
        return (time.time() - last) > max_age_seconds

    def latest_price(self, tradingsymbol: str, exchange: str = "NSE"):
        token = self.instrument_token(tradingsymbol, exchange)
        with self._lock:
            tick = self.ticks.get(token)
        return tick["last_price"] if tick else None

    def _on_connect(self, ws, response):
        ws.subscribe(self._subscribed_tokens)
        ws.set_mode(ws.MODE_FULL, self._subscribed_tokens)

    def _on_ticks(self, ws, ticks):
        with self._lock:
            for t in ticks:
                self.ticks[t["instrument_token"]] = t
                self._last_tick_at[t["instrument_token"]] = time.time()

    def _on_close(self, ws, code, reason):
        print(f"[market_data] ticker closed: {code} {reason}")

    def _on_error(self, ws, code, reason):
        print(f"[market_data] ticker error: {code} {reason}")

    def _on_reconnect(self, ws, attempts_count):
        print(f"[market_data] ticker reconnecting (attempt {attempts_count})")

    def _on_noreconnect(self, ws):
        # Reconnect attempts exhausted — this is a NO-TRADE condition (Section 11),
        # not something main.py should silently keep trading through.
        print("[market_data] CRITICAL: ticker gave up reconnecting. Feed is dead.")

    def wait_for_ticks(self, timeout=10):
        start = time.time()
        while not self.ticks and time.time() - start < timeout:
            time.sleep(0.25)
