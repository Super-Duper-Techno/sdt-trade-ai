"""
SDT Trade AI — trade log + daily report (Sections 25, 26).
"""
import csv
import os
from datetime import date, datetime

LOG_FILE = "trade_log.csv"
FIELDS = [
    "timestamp", "tradingsymbol", "direction", "entry", "exit", "qty",
    "stop", "target", "confidence", "regime", "reason", "pnl",
]


def log_trade(row: dict):
    is_new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({**row, "timestamp": datetime.now().isoformat()})


def daily_report(trading_date: str = None) -> dict:
    trading_date = trading_date or str(date.today())
    if not os.path.exists(LOG_FILE):
        return {"trades": 0}

    rows = []
    with open(LOG_FILE) as f:
        for r in csv.DictReader(f):
            if r["timestamp"].startswith(trading_date):
                rows.append(r)

    if not rows:
        return {"trades": 0}

    pnls = [float(r["pnl"]) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    return {
        "date": trading_date,
        "total_trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(rows) * 100, 1),
        "gross_profit": round(sum(wins), 2),
        "gross_loss": round(sum(losses), 2),
        "net_pnl": round(sum(pnls), 2),
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "max_win": round(max(pnls), 2),
        "max_loss": round(min(pnls), 2),
    }


def print_daily_report():
    r = daily_report()
    print("\n" + "=" * 40)
    print("SDT TRADE AI — DAILY REPORT")
    print("=" * 40)
    if r.get("trades") == 0:
        print("No trades today.")
    else:
        for k, v in r.items():
            print(f"{k:>16}: {v}")
    print("=" * 40 + "\n")
