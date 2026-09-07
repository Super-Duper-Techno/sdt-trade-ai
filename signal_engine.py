"""
SDT Trade AI — signal engine (Sections 4-5).

This module answers exactly one question: "Is this a potentially profitable
setup?" It NEVER places orders, sizes positions, or touches risk limits —
that separation is the entire point of the rulebook's architecture.

The default scorer below is a transparent, inspectable heuristic (trend
strength + momentum + volatility normalization), not a trained model. Swap
`SignalEngine.score()` for your own ML model — the only contract that
matters is the return shape: (score: int 0-100, direction: "LONG"|"SHORT"|None, regime: str).
"""
import numpy as np
import pandas as pd


REGIMES = ("TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY", "ABNORMAL")


def compute_features(df: pd.DataFrame) -> dict:
    """df must have a 'close' column of recent candles, most recent last."""
    closes = df["close"].values
    if len(closes) < 15:
        return {"valid": False}

    returns = np.diff(closes) / closes[:-1]
    atr_proxy = float(np.std(closes[-14:]))
    slope = float((closes[-1] - closes[-10]) / 10)
    momentum = float(np.mean(returns[-5:]) * 100)
    vol_ratio = float(np.std(returns[-5:]) / (np.std(returns[-20:]) + 1e-9)) if len(returns) >= 20 else 1.0

    return {
        "valid": True,
        "last_price": float(closes[-1]),
        "atr_proxy": atr_proxy,
        "slope": slope,
        "momentum": momentum,
        "vol_ratio": vol_ratio,
        "stddev_pct": float(atr_proxy / closes[-1] * 100),
    }


def classify_regime(features: dict) -> str:
    if not features.get("valid"):
        return "ABNORMAL"
    if features["stddev_pct"] > 1.2:
        return "HIGH_VOLATILITY"
    if features["stddev_pct"] < 0.15:
        return "LOW_VOLATILITY"
    if features["slope"] > features["atr_proxy"] * 0.15:
        return "TRENDING_UP"
    if features["slope"] < -features["atr_proxy"] * 0.15:
        return "TRENDING_DOWN"
    return "RANGING"


class SignalEngine:
    """Heuristic default — replace `score()` with a trained model if you have one."""

    STRATEGY_MAP = {
        "TRENDING_UP": "LONG",
        "TRENDING_DOWN": "SHORT",
        # ranging / high-vol / low-vol / abnormal are intentionally not traded
        # by this default trend-following strategy — extend here for mean-reversion.
    }

    def score(self, df: pd.DataFrame) -> dict:
        features = compute_features(df)
        regime = classify_regime(features)
        direction = self.STRATEGY_MAP.get(regime)

        if direction is None or not features.get("valid"):
            return {"score": 0, "direction": None, "regime": regime, "features": features}

        # Normalize momentum + trend strength into a 0-100 confidence score.
        trend_strength = min(abs(features["slope"]) / (features["atr_proxy"] + 1e-9), 3.0) / 3.0
        momentum_component = min(abs(features["momentum"]), 2.0) / 2.0
        vol_penalty = max(0.0, 1.0 - abs(features["vol_ratio"] - 1.0))

        raw = 0.5 * trend_strength + 0.3 * momentum_component + 0.2 * vol_penalty
        score = int(round(raw * 100))

        return {"score": score, "direction": direction, "regime": regime, "features": features}
