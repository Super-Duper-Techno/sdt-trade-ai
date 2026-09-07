# SDT Trade AI — one-click dashboard edition

A local web dashboard for the SDT trading rulebook, wired to Zerodha Kite
Connect. Runs identically on Windows, Mac, and Linux because it's just
Python + your browser — no native installers, no OS-specific builds.

```
MARKET DATA → FEATURE ENGINE → AI SIGNAL ENGINE → ENTRY RULE ENGINE →
RISK ENGINE → EXECUTION ENGINE → BROKER → POSITION MONITORING → AUTO-EXIT
```

## Quick start

**Windows** — double-click `run_windows.bat`
**Mac** — first time only: right-click `run_mac.command` → Open (macOS
blocks unsigned scripts on the first launch). After that, double-click it.
**Linux** — `chmod +x run_linux.sh` once, then double-click it, or run
`./run_linux.sh` in a terminal.

Each script creates a virtual environment, installs dependencies, and opens
`http://127.0.0.1:5000` in your browser automatically. First run takes
30–60 seconds to install; after that it's instant.

## Before the dashboard is useful

1. Create a Kite Connect app at https://developers.kite.trade (₹500/month
   subscription, separate from your regular Zerodha account).
2. `cp .env.example .env` and fill in `KITE_API_KEY` / `KITE_API_SECRET`.
3. Launch the app — the dashboard opens on a **Connect to Kite** screen.
   Click "Open Kite Login", log in with your Zerodha credentials, copy the
   `request_token` from the redirect URL, paste it back, click Connect.
   (Kite requires this once every trading day — there's no way around it
   without storing your Zerodha password, which this deliberately doesn't do.)

## What ships configured for a ₹5,000 test run

`config.json` defaults to:

- **Capital: ₹5,000**
- Risk per trade: 5% (₹250) — the rulebook's own 0.25–0.5% default produces
  a near-zero position size at ₹5,000 against most stock prices, so this
  is bumped up specifically to make test trades actually happen. Treat
  this as a functional-testing setting, not a recommended live one.
- Max daily loss: 10% (₹500)
- Max 3 trades/day, max 3 consecutive losses
- Instruments: IDEA, YESBANK — low-priced, liquid NSE stocks, chosen so a
  ₹5,000 account can actually take a meaningful position size in them

All of this is editable from the dashboard's Configuration panel — just
stop the engine first (config can't change mid-session).

## Paper mode — on by default

The dashboard's **Paper mode** toggle is ON by default. In paper mode the
engine uses real Kite market data but places zero real orders — fills are
simulated. Flip it off only when you've watched paper trades behave the
way you expect and are deliberately ready to place real orders with real
money. There's no confirmation dialog beyond the toggle itself, so treat
that switch with the seriousness it deserves.

## The dashboard

- **Live prices** for each configured instrument, with regime tags
  (trending up/down, ranging, high volatility)
- **Final Decision Engine** — the entry waterfall lighting up green/pass or
  red/fail in real time, same as the rulebook's Section 28
- **Open position card** with live unrealized P&L and R-multiple
- **Session stats** — daily P&L, trades today, consecutive losses, all
  against your configured limits
- **Start / Stop / Reset Day / Kill Switch** controls
- **Trade log** of everything closed this session

## Architecture (unchanged from the CLI version)

| File | Role |
|---|---|
| `app.py` | Flask server — dashboard + control API |
| `engine_runtime.py` | runs the pipeline in a background thread, publishes state |
| `paper_execution.py` | simulated fills for paper mode — real market data, no real orders |
| `config.py`, `auth.py`, `market_data.py`, `signal_engine.py`, `rule_engine.py`, `risk_engine.py`, `execution.py`, `position_monitor.py`, `gtt_safety.py`, `logger_store.py` | same engine as before — see RUNBOOK.md for the section-by-section mapping |
| `main.py` | still here as a terminal-only alternative if you don't want the dashboard |

## Tests

```
pip install pytest
python -m pytest tests/ -v
```

34 tests, run against a mocked Kite client, verifying the risk math, the
entry waterfall's every reject path, exit logic in both directions, and
the GTT backstop — with no live account needed. This is what "working"
means for the parts I can actually verify from here; the live broker
round-trip is the one thing only you can test, which is exactly what
paper mode exists to de-risk.

## Golden rule

> Protect capital first. Profit comes second. If the system is not sure,
> do nothing. A missed trade costs nothing. An uncontrolled trade can cost
> the account.
