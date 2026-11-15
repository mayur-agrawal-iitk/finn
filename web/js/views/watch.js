import { shortCo } from "../cards.js";
import { esc, logoText, num, pct, signCls, spark } from "../lib.js";
import { CATEGORY_LABEL } from "../rules.js";

export function renderWatch(ctx) {
  const { data, prefs } = ctx;
  const idx = data.eod["^NSEI"] || [];
  const iret = idx.length > 1 ? (idx[idx.length - 1][1] / idx[idx.length - 2][1] - 1) * 100 : null;
  const rows = data.portfolio.holdings.map((h) => {
    const s = data.eod[h.symbol] || [];
    const last = s[s.length - 1], prev = s[s.length - 2];
    const ret = last && prev ? (last[1] / prev[1] - 1) * 100 : null;
    const avg = s.length > 21 ? s.slice(-21, -1).reduce((a, r) => a + r[2], 0) / 20 : null;
    const vm = avg && last ? last[2] / avg : null;
    return { h, last, ret, vm, series: s.slice(-60).map((r) => r[1]) };
  });
  const lastDate = idx.length ? idx[idx.length - 1][0] : "";
  const stepper = (key, step, min, max, unit) => `<div class="stepper"><button data-step="${key}" data-d="${-step}" data-min="${min}" data-max="${max}" aria-label="decrease">−</button><output>${num(prefs[key], step < 1 ? 1 : 0)}${unit}</output><button data-step="${key}" data-d="${step}" data-min="${min}" data-max="${max}" aria-label="increase">+</button></div>`;
  const cats = Object.entries(CATEGORY_LABEL).filter(([k]) => k !== "unclassified");
  return `<div class="view">
    <header class="top"><div class="eyebrow">Watch</div><div class="h1">Your book &amp; your rules</div>
      <div class="sub">End of day ${lastDate ? new Date(lastDate).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : ""} · Nifty <span class="${signCls(iret)}">${pct(iret)}</span></div></header>

    <section class="section"><div class="section-head"><h2 class="h2">What counts as unusual</h2></div>
      <div class="card">
        <div class="setting"><div><div class="label">Volume spike</div><div class="hint">Day's volume vs its 20-day average</div></div>${stepper("volume_multiple", 0.5, 1, 10, "×")}</div>
        <div class="setting"><div><div class="label">Price move</div><div class="hint">Up or down in a single day</div></div>${stepper("price_move_pct", 0.5, 1, 20, "%")}</div>
        <div class="setting"><div><div class="label">Measure against Nifty</div><div class="hint">Ignore moves the whole market made</div></div>
          <label class="switch"><input type="checkbox" data-pref="relative_to_index" ${prefs.relative_to_index ? "checked" : ""}><span></span></label></div>
      </div></section>

    <section class="section"><div class="section-head"><h2 class="h2">Filings you care about</h2><span class="tiny muted">others sink to routine</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">${cats.map(([k, l]) => `<button class="chip ${prefs.care.includes(k) ? "on" : ""}" data-care="${esc(k)}">${esc(l)}</button>`).join("")}</div></section>

    <section class="section"><div class="section-head"><h2 class="h2">Holdings</h2><span class="count">${rows.length}</span></div>
      <div class="list">${rows.map((r) => {
        const flag = r.vm && r.vm >= prefs.volume_multiple;
        return `<a class="row" href="#/r/${r.h.symbol}"><span class="logo">${logoText(r.h.symbol)}</span>
          <span class="grow"><div class="title">${esc(shortCo(r.h.name))}</div><div class="meta">${r.h.weight}% · ${esc((r.h.sector || []).filter(Boolean).slice(-1)[0] || "")}${flag ? ` · <span style="color:var(--amber);font-weight:700">${num(r.vm, 1)}× vol</span>` : ""}</div></span>
          <span class="right">${spark(r.series, { w: 44, h: 22 })}</span>
          <span class="right" style="min-width:74px"><div class="num" style="font-weight:700">${r.last ? num(r.last[1], r.last[1] < 100 ? 2 : 0) : "—"}</div><div class="small ${signCls(r.ret)} num">${pct(r.ret)}</div></span></a>`;
      }).join("")}</div></section>

    <section class="section"><div class="section-head"><h2 class="h2">Under the hood</h2></div>
      <div class="card soft small"><dl class="kv">
        <dt>Data built</dt><dd>${new Date(data.meta.generated_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</dd>
        <dt>Filings tracked</dt><dd>${data.meta.counts.events} in 45 days</dd>
        <dt>Model outputs</dt><dd>${data.meta.llm.calls} cached · ${data.meta.llm.pending} queued</dd>
        <dt>Model cost</dt><dd>${data.meta.llm.usd ? `$${data.meta.llm.usd.toFixed(2)} actual` : ""}${data.meta.llm.est_usd ? `≈ $${data.meta.llm.est_usd.toFixed(2)} at API prices for everything above (${Math.round((data.meta.llm.est_input_tokens || 0) / 1000)}k tokens in)` : ""}</dd>
        <dt>Your settings</dt><dd>stored on this device only</dd></dl>
        <button class="link" style="margin-top:12px" data-reset>Reset rules &amp; dismissed items</button></div></section>
  </div>`;
}
