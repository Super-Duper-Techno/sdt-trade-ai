"""
SDT Trade AI — configuration.

All hard risk limits live here. Nothing in signal_engine.py or rule_engine.py
is allowed to change these at runtime — that's the whole point of the
rulebook (Section 27: CORE HARD RULES).
"""
import os
import json
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()


@dataclass
class RiskConfig:
    # --- account ---
    capital: float = 1_000_000.0

    # --- capital protection (Section 2 / Section 30 defaults) ---
    risk_per_trade_pct: float = 0.25          # % of capital risked per trade
    max_daily_loss_pct: float = 1.5           # % of capital — hard stop for the day
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 4
    allow_averaging_down: bool = False        # NEVER set True without a tested strategy
    allow_martingale: bool = False            # must always be False

    # --- entry thresholds ---
    min_ai_confidence: int = 70               # 0-100
    min_risk_reward: float = 2.0              # 1 : min_risk_reward

    # --- position sizing caps ---
    max_position_value_pct: float = 50.0      # % of capital in a single position
    max_leverage: float = 1.0                 # 1.0 = no leverage beyond capital

    # --- exits ---
    time_exit_minutes: int = 60
    trail_activate_r: float = 1.0             # move stop to breakeven at +1R
    trail_lock_r: float = 1.5                 # start trailing at +1.5R

    # --- spread / slippage filters ---
    max_spread_pct: float = 0.15              # reject entry if spread wider than this
    max_slippage_pct: float = 0.20            # flag / cooldown if breached on fill

    # --- session ---
    square_off_time: str = "15:15"            # IST, before actual market close 15:30
    market_open_time: str = "09:15"
    market_close_time: str = "15:30"

    # --- instruments this session trades ---
    tradingsymbols: tuple = ("RELIANCE", "TCS", "INFY")
    exchange: str = "NSE"
    product: str = "MIS"                      # intraday margin product on Kite

    def risk_amount(self) -> float:
        return round(self.capital * self.risk_per_trade_pct / 100, 2)

    def daily_loss_limit(self) -> float:
        return round(self.capital * self.max_daily_loss_pct / 100, 2)

    def max_position_value(self) -> float:
        return round(self.capital * self.max_position_value_pct / 100, 2)


def load_config(path: str = "config.json") -> RiskConfig:
    """Load overrides from config.json if present, else defaults."""
    cfg = RiskConfig()
    if os.path.exists(path):
        with open(path) as f:
            overrides = json.load(f)
        cfg = RiskConfig(**{**asdict(cfg), **overrides})
    assert cfg.allow_martingale is False, "Martingale must never be enabled (Section 2)."
    return cfg


KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")
