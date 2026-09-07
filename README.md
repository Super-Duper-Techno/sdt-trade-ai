# SDT Trade AI — One-Click Trading Dashboard

> **SUPER DUPER TECHNO — SDT Trade AI**

[

![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)

](https://www.buymeacoffee.com/superdupertechno)

A local web dashboard for the SDT trading rulebook, connected to
[Zerodha Kite Connect](https://developers.kite.trade/).

SDT Trade AI combines market data, feature analysis, signal generation,
entry rules, risk management, execution, position monitoring, and
automated exits into a single local dashboard.

It is designed to run on **Windows, macOS, and Linux** using Python and
a web browser. No native installer or OS-specific application build is
required.

---

> [!WARNING]
> ## ⚠️ Financial Risk
>
> **SDT Trade AI is experimental trading software.**
>
> The software can be configured to place real financial orders through
> Zerodha Kite Connect when Paper mode is disabled.
>
> **Paper mode is enabled by default.**
>
> Do not disable Paper mode until you have thoroughly tested the system,
> understand its behavior, and deliberately accept the risks of placing
> real orders.
>
> Trading involves the risk of financial loss. No profit, return, or
> performance is guaranteed.
>
> Market conditions, volatility, liquidity, slippage, network failures,
> broker outages, rejected orders, incorrect configuration, software
> bugs, and other unexpected conditions can result in losses.
>
> **Never trade money you cannot afford to lose.**
>
> SDT Trade AI is provided for experimental, educational, and
> technological purposes. It is not financial, investment, or trading
> advice.

---

## 🧭 Project Status

**Current version:** `0.1.0`
**Status:** Experimental / Initial Public Release

SDT Trade AI currently includes:

- ✅ Local web dashboard
- ✅ Zerodha Kite Connect integration
- ✅ Paper trading mode
- ✅ Live market-data integration
- ✅ Feature engine
- ✅ AI signal engine
- ✅ Entry rule engine
- ✅ Risk engine
- ✅ Execution engine
- ✅ Position monitoring
- ✅ Automated exit logic
- ✅ GTT safety backstop
- ✅ Session statistics
- ✅ Trade logging
- ✅ Kill switch
- ✅ Configuration dashboard
- ✅ Automated test suite
- ✅ Mocked Kite client tests
- ✅ Windows launcher
- ✅ macOS launcher
- ✅ Linux launcher

### What this status means

The project is functional and its tested components have automated
coverage.

However, **passing automated tests does not mean that live trading is
guaranteed to be safe or profitable**.

The test suite uses a mocked Kite client and therefore does not reproduce
every condition of a real broker connection or real financial market.

Live broker behavior, order execution, slippage, network conditions,
broker-side rejection, market volatility, and other real-world
conditions require separate validation.

---

# 📊 System Pipeline

SDT Trade AI follows the complete trading pipeline:

```text
MARKET DATA
     ↓
FEATURE ENGINE
     ↓
AI SIGNAL ENGINE
     ↓
ENTRY RULE ENGINE
     ↓
RISK ENGINE
     ↓
EXECUTION ENGINE
     ↓
BROKER
     ↓
POSITION MONITORING
     ↓
AUTO-EXIT