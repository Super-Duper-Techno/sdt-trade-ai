"""
SDT Trade AI — Zerodha Kite Connect authentication.

Two ways to use this:
1. CLI: `python auth.py` — interactive, prompts for the request_token.
2. Dashboard: get_login_url() + complete_login(request_token) — same flow,
   driven by app.py so it can happen inside the browser instead of a terminal.
"""
import json
import os
from datetime import date

from kiteconnect import KiteConnect

from config import KITE_API_KEY, KITE_API_SECRET

TOKEN_FILE = "token.json"


def new_kite_client() -> KiteConnect:
    if not KITE_API_KEY or not KITE_API_SECRET:
        raise RuntimeError(
            "Set KITE_API_KEY and KITE_API_SECRET in your .env file. "
            "Get these from https://developers.kite.trade after creating a Connect app."
        )
    return KiteConnect(api_key=KITE_API_KEY)


def get_login_url() -> str:
    return new_kite_client().login_url()


def complete_login(request_token: str) -> KiteConnect:
    """Exchanges a request_token (from the Kite login redirect) for a session,
    caches the access token for the rest of today, and returns a ready client."""
    kite = new_kite_client()
    session = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
    kite.set_access_token(session["access_token"])
    _cache_token(session["access_token"])
    return kite


def try_cached_session():
    """Returns a ready KiteConnect client if today's cached token still works, else None."""
    cached = _load_cached_token()
    if not cached:
        return None
    kite = new_kite_client()
    kite.set_access_token(cached)
    try:
        kite.profile()
        return kite
    except Exception:
        return None


def get_kite() -> KiteConnect:
    """CLI-only interactive flow."""
    kite = try_cached_session()
    if kite:
        return kite
    print("\nKite session expired or missing. Login here:")
    print(get_login_url())
    request_token = input("\nPaste the request_token from the redirect URL: ").strip()
    kite = complete_login(request_token)
    print("Session established and cached for today.\n")
    return kite


def _cache_token(token: str):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"date": str(date.today()), "access_token": token}, f)


def _load_cached_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    if data.get("date") != str(date.today()):
        return None
    return data.get("access_token")


if __name__ == "__main__":
    kite = get_kite()
    profile = kite.profile()
    print(f"Logged in as {profile['user_name']} ({profile['user_id']})")
