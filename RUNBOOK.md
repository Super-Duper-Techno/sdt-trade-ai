# RUNBOOK — first live session

Follow this in order. Don't skip steps to get to "live" faster — the
rulebook's own Section 24 staging exists because that's how people avoid
losing money to a bug on day one.

## 0. Prerequisites

- A funded Zerodha trading account, separate from your Kite Connect
  developer subscription (₹500/month, from https://developers.kite.trade)
- Python 3.10+
- `pip install -r requirements.txt`

## 1. Run the tests (no account needed)

```
cd sdt_trade_ai
pip install pytest
python -m pytest tests/ -v
```

All 34 should pass. This proves the risk math, the entry waterfall, the
exit logic, and the GTT backstop behave correctly in isolation — it does
NOT prove Kite's API responds the way this code assumes. That's step 4.

## 2. Paper trade with the simulator

Open the `sdt_trade_ai.jsx` dashboard built earlier. Run it for a few
sessions. Same rule waterfall, same risk math, simulated fills — this is
where you build trust in the *strategy*, not the broker plumbing.

## 3. Configure

```
cp .env.example .env        # fill in KITE_API_KEY / KITE_API_SECRET
```

Edit `config.json`. For your first live run:

```json
{
  "capital": 25000,
  "risk_per_trade_pct": 0.25,
  "max_daily_loss_pct": 1.0,
  "max_trades_per_day": 2,
  "tradingsymbols": ["RELIANCE"]
}
```

One instrument, tiny capital, tight daily loss cap. Widen this only after
you've watched it work correctly for real.

## 4. Dry run against live data, zero risk

Before letting it place a single order, run just the data layer and watch
the logs:

```python
from auth import get_kite
from config import load_config, KITE_API_KEY
from market_data import MarketData
from signal_engine import SignalEngine

cfg = load_config()
kite = get_kite()
md = MarketData(kite, kite.access_token, KITE_API_KEY)
md.start_ticker(cfg.tradingsymbols, cfg.exchange)
md.wait_for_ticks()

import time
for _ in range(20):
    print(md.latest_price(cfg.tradingsymbols[0], cfg.exchange))
    time.sleep(1)
```

Confirm: prices update, look sane, and `md.is_stale(...)` returns `False`
while this loop runs. If anything here looks wrong, stop — do not proceed
to step 5 until this is clean.

## 5. First live session

```
python auth.py     # once, every trading morning — paste the request_token
python main.py
```

Watch the terminal the entire session. It will log every rule-engine
rejection ("NO TRADE" is the expected common case — most ticks should
reject somewhere in the waterfall) and every approved trade with its
sizing and reasoning.

Stop it manually (Ctrl+C) at any point — `main.py`'s loop only opens one
position at a time and blocks on `monitor.watch()`, so if you interrupt
between trades nothing is left dangling. If you interrupt *while* a
position is open, the GTT backstop (Section: gtt_safety.py) is still live
on Kite's side and will close it even with the script dead — check
`kite.positions()` and `kite.get_gtts()` afterward to confirrm.

## 6. After the session

```python
from logger_store import print_daily_report
print_daily_report()
```

Read `trade_log.csv`. Check every trade's reasoning against what actually
happened in the market. Don't increase capital until several sessions
look the way you expect.

## If something looks wrong

Kill it immediately — either Ctrl+C, or from a Python shell:

```python
from risk_engine import RiskEngine
from config import load_config
risk = RiskEngine(load_config())
risk.manual_kill("investigating anomaly")
```

Then manually check `kite.positions()` on the Kite web/app UI directly —
don't trust this codebase's own state once something's already looked
wrong once.
