const $ = (id) => document.getElementById(id);

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  return res.json();
}

let configLoadedOnce = false;

function fmt(n) {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function regimeClass(regime) {
  if (!regime) return "";
  if (regime.includes("UP")) return "up";
  if (regime.includes("DOWN")) return "down";
  if (regime.includes("VOLATILITY")) return "vol";
  return "";
}

function render(state) {
  // connect screen vs dashboard
  $("connectPanel").classList.toggle("hidden", state.connected);
  $("mainDashboard").classList.toggle("hidden", !state.connected);
  if (!state.connected) return;

  // header pills
  $("modePill").textContent = state.paper_mode ? "PAPER MODE" : "LIVE — REAL ORDERS";
  $("modePill").style.color = state.paper_mode ? "var(--info)" : "var(--danger)";
  $("modePill").style.borderColor = state.paper_mode ? "var(--info)" : "var(--danger)";

  const statusPill = $("statusPill");
  statusPill.textContent = state.status.toUpperCase();
  statusPill.className = "pill status-pill " + state.status;

  // kill banner
  const killed = state.kill_switch && state.kill_switch.active;
  $("killBanner").classList.toggle("hidden", !killed);
  if (killed) $("killReason").textContent = `TRADING HALTED — ${state.kill_switch.reason}`;

  // config form (only populate once so typing isn't overwritten)
  if (!configLoadedOnce) {
    const c = state.config;
    $("cfgCapital").value = c.capital;
    $("cfgRisk").value = c.risk_per_trade_pct;
    $("cfgDailyLoss").value = c.max_daily_loss_pct;
    $("cfgConsecLoss").value = c.max_consecutive_losses;
    $("cfgMaxTrades").value = c.max_trades_per_day;
    $("cfgConfidence").value = c.min_ai_confidence;
    $("cfgRR").value = c.min_risk_reward;
    $("cfgSymbols").value = c.tradingsymbols.join(", ");
    $("paperToggle").checked = state.paper_mode;
    configLoadedOnce = true;
  }

  // prices + regime tags
  const priceGrid = $("priceGrid");
  priceGrid.innerHTML = "";
  Object.entries(state.prices).forEach(([sym, price]) => {
    const div = document.createElement("div");
    div.className = "price-item";
    div.innerHTML = `<div class="sym">${sym}</div><div class="val">₹${fmt(price)}</div>`;
    priceGrid.appendChild(div);
  });
  const regimeTags = $("regimeTags");
  regimeTags.innerHTML = "";
  Object.entries(state.regime || {}).forEach(([sym, regime]) => {
    const span = document.createElement("span");
    span.className = "regime-tag " + regimeClass(regime);
    span.textContent = regime;
    regimeTags.appendChild(span);
  });

  // last signal
  const sig = state.last_signal;
  $("signalRow").innerHTML = sig
    ? `AI signal — <b>${sig.symbol}</b> score <b>${sig.score}</b> · ${sig.direction || "no direction"} · ${sig.regime}`
    : "";

  // waterfall
  const wf = $("waterfall");
  wf.innerHTML = "";
  state.waterfall.forEach((s) => {
    const row = document.createElement("div");
    row.className = "step " + s.state;
    row.innerHTML = `<span class="dot"></span><span>${s.label}</span>` +
      (s.state === "fail" ? `<span class="tag">NO TRADE</span>` : "");
    wf.appendChild(row);
  });

  // position card
  const posCard = $("positionCard");
  if (state.position) {
    const p = state.position;
    const pnlClass = p.unrealized >= 0 ? "pos-v" : "neg-v";
    posCard.innerHTML = `
      <div class="stat-line"><span class="k">${p.tradingsymbol}</span><span class="v">${p.direction}</span></div>
      <div class="stat-line"><span class="k">Entry</span><span class="v">₹${fmt(p.entry)}</span></div>
      <div class="stat-line"><span class="k">Stop</span><span class="v neg-v">₹${fmt(p.stop)}</span></div>
      <div class="stat-line"><span class="k">Target</span><span class="v pos-v">₹${fmt(p.target)}</span></div>
      <div class="stat-line"><span class="k">Qty</span><span class="v">${p.qty}</span></div>
      <div class="stat-line"><span class="k">R-multiple</span><span class="v">${fmt(p.r_multiple)}R</span></div>
      <div class="stat-line"><span class="k">Unrealized</span><span class="v ${pnlClass}">₹${fmt(p.unrealized)}</span></div>
    `;
  } else {
    posCard.innerHTML = `<div class="muted">No position open — engine is scanning.</div>`;
  }

  // session stats
  const pnlClass = state.daily_pnl >= 0 ? "pos-v" : "neg-v";
  const dailyLossLimit = (state.config.capital * state.config.max_daily_loss_pct) / 100;
  $("sessionStats").innerHTML = `
    <div class="stat-line"><span class="k">Daily P&L</span><span class="v ${pnlClass}">₹${fmt(state.daily_pnl)}</span></div>
    <div class="stat-line"><span class="k">Daily loss limit</span><span class="v">₹${fmt(dailyLossLimit)}</span></div>
    <div class="stat-line"><span class="k">Trades today</span><span class="v">${state.trades_today} / ${state.config.max_trades_per_day}</span></div>
    <div class="stat-line"><span class="k">Consecutive losses</span><span class="v ${state.consecutive_losses > 0 ? "warn-v" : ""}">${state.consecutive_losses} / ${state.config.max_consecutive_losses}</span></div>
  `;

  // trade log
  const logBody = $("logBody");
  if (state.trade_log.length === 0) {
    logBody.innerHTML = `<tr><td colspan="7" class="muted center">No trades yet this session.</td></tr>`;
  } else {
    logBody.innerHTML = state.trade_log.map((t) => {
      const pnlClass = t.pnl >= 0 ? "pos-v" : "neg-v";
      const dirClass = t.direction === "LONG" ? "pos-v" : "neg-v";
      return `<tr>
        <td>${t.symbol}</td><td class="${dirClass}">${t.direction}</td>
        <td>₹${fmt(t.entry)}</td><td>₹${fmt(t.exit)}</td><td>${t.qty}</td>
        <td class="muted">${t.reason}</td><td class="${pnlClass}">₹${fmt(t.pnl)}</td>
      </tr>`;
    }).join("");
  }

  // button enable/disable
  const running = ["scanning", "in_position", "halted", "connecting"].includes(state.status);
  $("startBtn").disabled = running;
  $("stopBtn").disabled = !running;
  $("saveConfigBtn").disabled = running;
  $("paperToggle").disabled = running;

  // kill/resume toggle
  const killBtn = $("killBtn");
  if (killed) {
    killBtn.textContent = "✓ Resume Trading";
    killBtn.classList.remove("btn-danger");
    killBtn.classList.add("btn-safe");
  } else {
    killBtn.textContent = "⏻ Kill Switch";
    killBtn.classList.remove("btn-safe");
    killBtn.classList.add("btn-danger");
  }
}

async function poll() {
  try {
    const state = await api("/api/state");
    render(state);
  } catch (e) { /* server not ready yet */ }
  setTimeout(poll, 1200);
}

// ---- wiring ----
$("loginBtn").onclick = async () => {
  const res = await api("/api/login_url");
  if (res.url) window.open(res.url, "_blank");
  else $("connectError").textContent = res.error || "Could not get login URL.";
};

$("connectBtn").onclick = async () => {
  const token = $("requestTokenInput").value.trim();
  if (!token) return;
  const res = await api("/api/connect", "POST", { request_token: token });
  $("connectError").textContent = res.ok ? "" : (res.error || "Connection failed.");
};

$("saveConfigBtn").onclick = async () => {
  const body = {
    capital: parseFloat($("cfgCapital").value),
    risk_per_trade_pct: parseFloat($("cfgRisk").value),
    max_daily_loss_pct: parseFloat($("cfgDailyLoss").value),
    max_consecutive_losses: parseInt($("cfgConsecLoss").value),
    max_trades_per_day: parseInt($("cfgMaxTrades").value),
    min_ai_confidence: parseInt($("cfgConfidence").value),
    min_risk_reward: parseFloat($("cfgRR").value),
    tradingsymbols: $("cfgSymbols").value,
  };
  const res = await api("/api/config", "POST", body);
  $("configError").textContent = res.ok ? "" : (res.error || "Could not save config.");
};

$("paperToggle").onchange = async () => {
  await api("/api/paper_mode", "POST", { enabled: $("paperToggle").checked });
};

$("startBtn").onclick = () => api("/api/start", "POST");
$("stopBtn").onclick = () => api("/api/stop", "POST");
$("resetBtn").onclick = () => api("/api/reset_day", "POST");
$("killBtn").onclick = () => {
  if ($("killBtn").textContent.includes("Kill")) {
    api("/api/kill", "POST");
  } else {
    api("/api/resume", "POST");
  }
};

poll();
