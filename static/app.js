/* Trade Radar Web – front-end (Plotly) */
(() => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ASSETS = [["BTCUSD", "Bitcoin"], ["XAUUSD", "ทองคำ"], ["EURUSD", "EUR/USD"]];
  const KEYS = ["E1", "E2", "E3", "E4", "E5", "E6"];
  const C = { bg: "rgba(0,0,0,0)", grid: "#353a45", green: "#26a69a", red: "#ef5350", pink: "#ff2d7a", blue: "#2979ff", orange: "#ff9800", white: "#d0d4dc", purple: "#b388ff", muted: "#80868f" };
  const S = { asset: localStorage.getItem("tr_asset") || "XAUUSD", tf: localStorage.getItem("tr_tf") || "4h", side: "auto", showOI: true, data: {}, timer: null, nextAt: 0 };
  const fmtP = (v, d) => (v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const thTime = (iso, opt = { dateStyle: "medium", timeStyle: "short" }) => (iso ? new Date(iso).toLocaleString("th-TH", { timeZone: "Asia/Bangkok", ...opt }) : "—");
  const cfg = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
  const font = { family: '"IBM Plex Sans Thai", system-ui, sans-serif', color: C.white, size: 11 };

  // ---------- controls ----------
  function seg(id, attr, key) {
    document.querySelectorAll(`#${id} button`).forEach((b) => {
      b.classList.toggle("on", b.dataset[attr] === S[key]);
      b.onclick = () => { S[key] = b.dataset[attr]; localStorage.setItem("tr_" + key, S[key]); seg(id, attr, key); load(); };
    });
  }
  seg("tf-seg", "tf", "tf");
  seg("side-seg", "side", "side");
  $("#show-oi").onchange = (e) => { S.showOI = e.target.checked; renderMain(); };
  $("#refresh").onclick = () => load(true);
  $("#refresh-sel").onchange = schedule;

  async function fetchJSON(url, opt) {
    const r = await fetch(url, opt);
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error || j.detail) throw new Error(j.error || j.detail || r.statusText);
    return j;
  }

  // ---------- load ----------
  async function load(force = false) {
    const btn = $("#refresh");
    btn.classList.add("busy"); btn.disabled = true;
    $("#err").classList.add("hidden");
    const bust = force ? `&t=${Date.now()}` : "";
    const jobs = ASSETS.map(([k]) => fetchJSON(`/api/analysis?asset=${k}&tf=${S.tf}&side=${k === S.asset ? S.side : "auto"}${bust}`)
      .then((d) => (S.data[k] = d)).catch((e) => (S.data[k] = { error: e.message })));
    // render the selected asset as soon as it arrives
    const mainJob = jobs[ASSETS.findIndex(([k]) => k === S.asset)];
    try {
      await mainJob;
      renderAll();
      await Promise.all(jobs);
      renderSummary();
    } finally {
      btn.classList.remove("busy"); btn.disabled = false;
      S.nextAt = Date.now() + (+$("#refresh-sel").value || 0) * 1000;
    }
    loadStatus();
  }
  function schedule() {
    clearInterval(S.timer);
    S.timer = setInterval(() => {
      const sec = +$("#refresh-sel").value;
      if (sec && Date.now() >= S.nextAt) load();
      tick();
    }, 1000);
    S.nextAt = Date.now() + (+$("#refresh-sel").value || 0) * 1000;
  }
  function tick() {
    const d = S.data[S.asset];
    if (!d || d.error) return;
    const sec = +$("#refresh-sel").value, left = Math.max(0, Math.round((S.nextAt - Date.now()) / 1000));
    $("#asof-sub").textContent = `แท่งล่าสุด ${thTime(d.last_bar, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` + (sec ? ` · รีเฟรชใน ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "");
  }

  function renderAll() { renderSummary(); renderMain(); }

  // ---------- summary cards ----------
  function renderSummary() {
    $("#summary").innerHTML = ASSETS.map(([k, n]) => {
      const d = S.data[k];
      if (!d) return `<div class="sum card ${k === S.asset ? "on" : ""}" data-k="${k}"><b>${k}</b> · ${n}<div class="muted">กำลังโหลด…</div></div>`;
      if (d.error) return `<div class="sum card ${k === S.asset ? "on" : ""}" data-k="${k}"><b>${k}</b> · ${n}<div class="err-s">โหลดไม่ได้: ${esc(d.error)}</div></div>`;
      const c = d.composite, dot = c >= 15 ? "🟢" : c <= -15 ? "🔴" : "⚪";
      return `<div class="sum card ${k === S.asset ? "on" : ""}" data-k="${k}">
        <div class="sum-h"><b>${k}</b><span class="muted">${esc(n)}</span></div>
        <div class="sum-p">${fmtP(d.price, d.decimals)} <span class="${d.change_pct >= 0 ? "up" : "dn"}">${d.change_pct >= 0 ? "+" : ""}${fmtP(d.change_pct, 2)}%</span></div>
        <div>${dot} <b>${esc(d.bias)}</b> (${c >= 0 ? "+" : ""}${Math.round(c)}) · Edge ${d.edges.count}/6</div>
        <div class="muted small">${esc(d.edges.status)}</div></div>`;
    }).join("");
    document.querySelectorAll(".sum").forEach((el) => (el.onclick = () => { S.asset = el.dataset.k; localStorage.setItem("tr_asset", S.asset); renderAll(); if (!S.data[S.asset] || S.side !== "auto") load(); }));
  }

  // ---------- main ----------
  function renderMain() {
    const d = S.data[S.asset];
    if (!d) return;
    if (d.error) { $("#err").textContent = `${S.asset}: ${d.error}`; $("#err").classList.remove("hidden"); return; }
    $("#asof").textContent = `อัปเดต ${thTime(d.asof)} น.`;
    $("#live-dot").classList.toggle("stale", (d.errors || []).length > 0);
    tick();
    priceChart(d); dirRadar(d); edgeRadar(d); narrative(d); dirDetail(d); edgeDetail(d); oiBox(d);
  }

  function priceChart(d) {
    const e = d.edges, dec = d.decimals, c = d.candles;
    $("#chart-title").textContent = `${d.asset} · ${d.name} · ${d.tf}`;
    $("#chart-meta").textContent = `${fmtP(d.price, dec)} · ${e.side} ${e.entry_kind}`;
    const x0 = c.t[0], x1 = c.t[c.t.length - 1];
    const hl = (y, color, dash, width = 1.4) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y, line: { color, dash, width } });
    const ann = (y, text, color) => ({ xref: "paper", x: 1, y, xanchor: "left", text, showarrow: false, font: { color, size: 10.5 }, bgcolor: "rgba(5,7,11,.7)" });
    const shapes = [
      { type: "rect", xref: "x", x0, x1, y0: e.range[0], y1: e.range[1], fillcolor: "rgba(200,205,215,0.04)", line: { width: 0 } },
      hl((e.range[0] + e.range[1]) / 2, "#555b66", "dot", 1),
      hl(e.entry, C.pink, "solid"), hl(e.tp, C.blue, "dash"), hl(e.sl, C.orange, "dash"), hl(d.price, C.white, "dot", 1),
    ];
    const anns = [ann(e.entry, `Entry ${fmtP(e.entry, dec)}`, C.pink), ann(e.tp, `TP ${fmtP(e.tp, dec)}`, C.blue), ann(e.sl, `SL ${fmtP(e.sl, dec)}`, C.orange)];
    if (S.showOI) for (const l of d.oi_levels || []) { shapes.push(hl(l.price, C.purple, "dash", 1)); anns.push({ ...ann(l.price, l.label, C.purple), x: 0, xanchor: "left" }); }
    const crypto = d.asset === "BTCUSD";
    Plotly.react("price-chart", [{
      type: "candlestick", x: c.t, open: c.o, high: c.h, low: c.l, close: c.c, name: d.asset,
      increasing: { line: { color: C.green }, fillcolor: C.green }, decreasing: { line: { color: C.red }, fillcolor: C.red },
    }], {
      paper_bgcolor: C.bg, plot_bgcolor: C.bg, font, margin: { l: 10, r: 110, t: 10, b: 30 }, showlegend: false, dragmode: "pan",
      xaxis: { rangeslider: { visible: false }, gridcolor: "#1d2129", rangebreaks: crypto ? [] : [{ bounds: ["sat", "mon"] }] },
      yaxis: { side: "right", gridcolor: "#1d2129", tickformat: dec >= 4 ? `.${dec}f` : ",." + dec + "f" },
      shapes, annotations: anns,
    }, cfg);
  }

  function polarLayout(extra = {}) {
    return {
      paper_bgcolor: C.bg, font, margin: { l: 70, r: 70, t: 46, b: 46 }, showlegend: false,
      polar: { gridshape: "linear", bgcolor: C.bg, radialaxis: { range: [0, 100], tickvals: [50, 100], showticklabels: false, gridcolor: C.grid, griddash: "dash", linecolor: "rgba(0,0,0,0)" },
        angularaxis: { direction: "clockwise", rotation: 90, gridcolor: C.grid, linecolor: C.grid, tickfont: { size: 11, color: C.white } } },
      ...extra,
    };
  }
  const close = (a) => [...a, a[0]];

  function dirRadar(d) {
    const names = Object.keys(d.axes), scores = names.map((n) => d.axes[n].score);
    const miss = new Set(d.missing || []);
    const labels = names.map((n, i) => `<span style="color:${miss.has(n) ? C.muted : scores[i] > 5 ? C.green : scores[i] < -5 ? C.red : C.muted}"><b>${n}</b><br>${miss.has(n) ? "ไม่มีข้อมูล" : (scores[i] > 0 ? "+" : "") + Math.round(scores[i])}</span>`);
    const col = d.composite >= 0 ? C.green : C.red;
    $("#bias-chip").textContent = `${d.bias} (${d.composite >= 0 ? "+" : ""}${Math.round(d.composite)})`;
    $("#bias-chip").className = "chip " + (d.composite >= 15 ? "bull" : d.composite <= -15 ? "bear" : "");
    Plotly.react("dir-radar", [
      { type: "scatterpolar", r: close(names.map(() => 50)), theta: close(labels), mode: "lines", line: { color: "#6b7280", dash: "dash", width: 1 }, hoverinfo: "skip" },
      { type: "scatterpolar", r: close(scores.map((s) => 50 + s / 2)), theta: close(labels), mode: "lines+markers", fill: "toself",
        fillcolor: col === C.green ? "rgba(38,166,154,.18)" : "rgba(239,83,80,.18)", line: { color: col, width: 2 }, marker: { size: 5 },
        text: close(names.map((n, i) => `${n}: ${(scores[i] > 0 ? "+" : "") + Math.round(scores[i])}<br>${(d.axes[n].reasons || [])[0] || ""}`)), hovertemplate: "%{text}<extra></extra>" },
    ], polarLayout(), cfg);
  }

  function edgeRadar(d) {
    const e = d.edges, p = d.prev, gates = new Set(d.gates);
    const labels = KEYS.map((k) => {
      const ok = e.passed[k], g = gates.has(k), color = ok ? C.white : g ? C.red : C.muted;
      return `<span style="color:${color}"><b>${k} ${d.names[k]}${g ? " ◆" : ""}</b><br>${Math.round(e.edges[k])}% ${ok ? "✓" : g ? "✗" : ""}${k === "E6" ? " · 1:" + (e.rr ?? 0).toFixed(1) : ""}</span>`;
    });
    const chip = $("#edge-chip");
    chip.textContent = `${e.side} · ${e.count}/6`;
    chip.className = "chip " + (e.failed_gates.length ? "bear" : e.count >= 5 ? "bull" : "");
    Plotly.react("edge-radar", [
      { type: "scatterpolar", r: close(KEYS.map((k) => p.edges[k])), theta: close(labels), mode: "lines", line: { color: C.orange, dash: "dash", width: 1.5 }, hoverinfo: "skip" },
      { type: "scatterpolar", r: close(KEYS.map((k) => e.edges[k])), theta: close(labels), mode: "lines+markers", fill: "toself", fillcolor: "rgba(200,205,215,.10)",
        line: { color: "#b8bcc6", width: 2 }, marker: { size: 4 }, text: close(KEYS.map((k) => `${k} ${d.names[k]}: ${Math.round(e.edges[k])}%<br>${esc(e.detail[k])}`)), hovertemplate: "%{text}<extra></extra>" },
    ], polarLayout(), cfg);
  }

  function narrative(d) {
    $("#narrative").innerHTML = d.narrative.map((l, i) => `<p class="${i === 0 ? "lead" : l.startsWith("  •") ? "hint" : ""}">${esc(l)}</p>`).join("") +
      ((d.errors || []).length ? `<p class="warn">⚠️ แหล่งข้อมูลที่โหลดไม่ได้: ${d.errors.map(esc).join(" | ")}</p>` : "");
  }

  function dirDetail(d) {
    $("#w-note").textContent = `น้ำหนัก (${d.tf}): ` + Object.entries(d.weights).map(([k, v]) => `${k} ${v}%`).join(" · ");
    const miss = new Set(d.missing || []);
    $("#dir-detail").innerHTML = Object.entries(d.axes).map(([n, a]) => {
      const s = a.score, m = miss.has(n);
      return `<div class="it"><div class="it-h"><b>${esc(n)}</b><span class="badge ${m ? "" : s > 5 ? "bull" : s < -5 ? "bear" : ""}">${m ? "ไม่นับ" : (s > 0 ? "+" : "") + Math.round(s)}</span><span class="muted">น้ำหนัก ${d.weights[n]}%</span></div>
        <div class="it-b">${a.reasons.map(esc).join(" · ")}</div></div>`;
    }).join("");
  }

  function edgeDetail(d) {
    const e = d.edges, gates = new Set(d.gates);
    $("#edge-detail").innerHTML = KEYS.map((k) => {
      const ok = e.passed[k], g = gates.has(k);
      return `<div class="it"><div class="it-h">${ok ? "✅" : g ? "⛔" : "▫️"} <b>${k} ${esc(d.names[k])}</b>${g ? '<span class="gate">◆ ด่านบังคับ</span>' : ""}<span class="badge">${Math.round(e.edges[k])}%</span></div>
        <div class="it-b">${esc(e.detail[k])}</div></div>`;
    }).join("") + `<p class="muted small">แผน ${e.side} ${e.entry_kind}: Entry ${fmtP(e.entry, d.decimals)} · SL ${fmtP(e.sl, d.decimals)} · TP ${fmtP(e.tp, d.decimals)} · RR 1:${(e.rr ?? 0).toFixed(1)}</p>`;
  }

  function oiBox(d) {
    const m = d.oi;
    if (!m) { $("#oi-meta").textContent = ""; $("#oi-box").innerHTML = `<p class="muted">ยังไม่มีข้อมูล OI ของสินทรัพย์นี้ → ดึงด้วย gold-oi-fetch แล้วนำเข้าที่การ์ด "นำเข้า OI" ด้านล่าง</p>`; return; }
    $("#oi-meta").textContent = `${m.series} · ${m.src || "CME"} · ดึงเมื่อ ${thTime(new Date(m.t_ms).toISOString())}` + (m.expired ? " · ⛔ หมดอายุ (ไม่นับคะแนน)" : ` · เหลือ ${m.dte} วัน`);
    $("#oi-box").innerHTML = `<div class="tiles">
        ${[["Scenario", m.scen + (m.experimental ? " ⚗️" : "")], ["Put/Call OI", m.pcr?.toFixed(2)], ["Max Pain", fmtP(m.max_pain, d.decimals > 2 ? 4 : 0)], ["IV · 1SD", `${m.iv?.toFixed(1)}% · ±${fmtP(m.sd, d.decimals > 2 ? 4 : 0)}`]]
          .map(([k, v]) => `<div class="tile"><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>
      ${m.top?.length ? `<p><b>Top Local OI (±1SD):</b> ${m.top.map((t) => `<code>${t.K}</code> ${t.share.toFixed(0)}% (C ${Math.round(t.C)} / P ${Math.round(t.P)})`).join(" · ")}</p>` : ""}
      <p class="muted small">${(m.score_reasons || []).map(esc).join(" · ")}</p>
      <p class="muted small">ΔD ${m.dD} (cut ${m.cut}) · ΔHHI ${m.dH}${d.basis ? ` · strike เป็นราคา 6E futures · basis ${d.basis.toFixed(5)} (เส้นบนกราฟปรับเป็น spot แล้ว)` : ""}${m.experimental ? " · ⚗️ EUR/BTC: cut ยังเป็นค่าทดลอง ให้น้ำหนักครึ่งหนึ่ง" : ""}</p>`;
  }

  // ---------- status / tools ----------
  async function loadStatus(check = false) {
    try {
      const s = await fetchJSON("/api/status" + (check ? "?check=1" : ""));
      const st = s.selftest ? `<p class="${s.selftest.ok ? "ok" : "warn"}">ทดสอบที่เก็บข้อมูล: ${s.selftest.ok ? "✅ เขียน/อ่านได้" : "❌ " + esc(s.selftest.error || "อ่านค่ากลับไม่ตรง")}</p>` : "";
      $("#status-box").innerHTML = `<p class="muted">ที่เก็บข้อมูล: <b>${s.backend === "vercel-blob" ? "Vercel Blob ✅" : "ชั่วคราว (ยังไม่ได้เชื่อม Vercel Blob — ข้อมูลที่นำเข้าจะหายเมื่อระบบรีสตาร์ต)"}</b> · OI ที่ควรมีล่าสุด: ${s.expected_oi_date}</p>${st}
        <table class="tbl"><tr><th>สินทรัพย์</th><th>Series</th><th>OI / Snapshot</th><th>หมดอายุ</th><th>หมายเหตุ</th></tr>
        ${s.assets.map((a) => `<tr class="${a.due ? "due" : ""}"><td>${a.asset}</td><td>${esc(a.series)}</td><td>${a.oi_date ? "OI " + a.oi_date + " · " : ""}${a.t_ms ? thTime(new Date(a.t_ms).toISOString(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}</td>
          <td>${a.e_ms ? thTime(new Date(a.e_ms).toISOString(), { day: "numeric", month: "short" }) + (a.dte != null ? ` (${a.dte > 0 ? "อีก " + a.dte + " วัน" : "หมดอายุ"})` : "") : "—"}</td><td>${esc(a.note)}</td></tr>`).join("")}</table>`;
    } catch (e) { $("#status-box").innerHTML = `<p class="warn">โหลดสถานะไม่ได้: ${esc(e.message)}</p>`; }
  }
  $("#selftest").onclick = () => loadStatus(true);
  $("#admin-token").value = localStorage.getItem("tr_admin_token") || "";
  $("#loi-save").onclick = async () => {
    const token = $("#admin-token").value.trim();
    localStorage.setItem("tr_admin_token", token);
    $("#loi-result").textContent = "กำลังบันทึก…";
    try {
      const r = await fetchJSON("/api/oi", { method: "POST", headers: { "content-type": "application/json", "x-admin-token": token },
        body: JSON.stringify({ loi: $("#loi-text").value, fut: $("#loi-fut").value.trim() || null, oi_date: $("#loi-date").value.trim() || null }) });
      $("#loi-result").textContent = "✅ บันทึกแล้ว: " + r.saved.map((s) => `${s.asset} ${s.series} (${s.strikes} strikes)`).join(" · ");
      $("#loi-text").value = "";
      load(true);
    } catch (e) { $("#loi-result").textContent = "❌ " + e.message; }
  };
  $("#copy").onclick = async () => {
    const d = S.data[S.asset];
    if (!d) return;
    try { await navigator.clipboard.writeText(`Trade Radar · ${d.asset} ${d.tf} · ${thTime(d.asof)}\n` + d.narrative.join("\n")); $("#copy").textContent = "คัดลอกแล้ว ✓"; }
    catch { $("#copy").textContent = "คัดลอกไม่ได้"; }
    setTimeout(() => ($("#copy").textContent = "คัดลอก"), 1600);
  };
  const g = $("#guide");
  $("#help-btn").onclick = () => g.showModal();
  $("#guide-close").onclick = () => g.close();
  g.onclick = (e) => { if (e.target === g) g.close(); };

  renderSummary();
  schedule();
  load();
})();
