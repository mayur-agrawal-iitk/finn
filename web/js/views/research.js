import { eventRow, shortCo, whoToCallBlock } from "../cards.js";
import { bars, esc, ICON, initials, inr, logoText, num, pct, signCls, spark, stack } from "../lib.js";

const STATUS = {
  delivered: ["Delivered", "pos"], on_track: ["On track", "pos"], missed: ["Missed", "neg"], at_risk: ["At risk", "amber"],
  walked_back: ["Walked back", "neg"], pending: ["Pending", ""], unverifiable: ["Can't verify", ""],
};
const STATUS_COLOR = { delivered: "var(--pos)", on_track: "#5fc79b", missed: "var(--neg)", at_risk: "#e0a100", walked_back: "#f08a8a", pending: "#c9ced6", unverifiable: "#e3e6ea" };
const METRIC = { revenue_growth: "Revenue growth", revenue: "Revenue", ebitda_margin: "EBITDA margin", ebitda: "EBITDA", pat_growth: "Profit growth", pat: "Profit",
  capex: "Capex", order_book: "Order book", order_inflow: "Order inflow", volume_growth: "Volume growth", capacity: "Capacity", debt: "Debt", working_capital: "Working capital",
  asset_quality: "Asset quality", loan_growth: "Loan growth", nim: "NIM", credit_cost: "Credit cost", roe_roa: "ROE/ROA", segment: "Segment", product_or_launch: "Launch", other: "Other" };

export function renderResearchHome(ctx) {
  const idx = ctx.data.index || [];
  const research = idx.filter((x) => !x.in_portfolio);
  const port = idx.filter((x) => x.in_portfolio);
  const item = (x) => `<a class="row" href="#/r/${x.symbol}"><span class="logo">${logoText(x.symbol)}</span>
    <span class="grow"><div class="title">${esc(shortCo(x.name))}</div><div class="meta">${esc((x.sector || []).filter(Boolean).join(" · "))}</div></span>
    <span class="right">${x.has_analysis ? '<span class="pill blue">Promises read</span>' : '<span class="pill">Numbers</span>'}</span></a>`;
  return `<div class="view">
    <header class="top"><div class="eyebrow">Pull</div><div class="h1">Research any company</div>
      <div class="sub">Grounded only in what the company itself filed — reported financials and its own earnings-call transcripts. No news, no broker notes.</div></header>
    <form class="ask" data-ask="research"><span>${ICON.search}</span><input name="q" placeholder="Company or NSE symbol, e.g. SRF, Dixon" autocomplete="off" list="symbols"></form>
    <datalist id="symbols">${(ctx.data.symbols || []).slice(0, 4000).map(([s, n]) => `<option value="${esc(s)}">${esc(n)}</option>`).join("")}</datalist>
    <section class="section"><div class="section-head"><h2 class="h2">Research set</h2><span class="count">${research.length}</span></div><div class="list">${research.map(item).join("")}</div></section>
    <section class="section"><div class="section-head"><h2 class="h2">Your holdings</h2><span class="count">${port.length}</span></div><div class="list">${port.map(item).join("")}</div></section>
    <p class="note" style="margin-top:20px">The engine is ticker-agnostic: point it at any NSE symbol. This static build carries ${idx.length} pre-computed dossiers; ${ctx.api || ctx.live ? "anything else is computed live — try a symbol you didn't see here." : "anything else needs the live engine (<code>python -m finn serve</code>)."}</p>
  </div>`;
}

export async function loadDossier(sym, ctx) {
  try {
    const r = await fetch(`data/research/${sym}.json`, { cache: "no-cache" });
    if (r.ok) return await r.json();
  } catch { /* fall through */ }
  if (ctx.api || ctx.live) {
    try {
      const r = await fetch(`${ctx.api ? ctx.api + "/" : ""}api/research/${encodeURIComponent(sym)}`);
      if (r.ok) return await r.json();
    } catch { /* offline */ }
  }
  return null;
}

export function renderMissing(sym, ctx) {
  const known = (ctx.data.symbols || []).find(([s]) => s === sym);
  return `<div class="view"><a class="back" href="#/research">${ICON.back} Research</a>
    <div class="empty"><div class="h2">${esc(known ? known[1] : sym)}</div>
    <p>${known ? "This company isn't in the static snapshot." : "That isn't an NSE symbol we recognise."}</p>
    ${known ? `<p class="small">The research engine works on any NSE symbol — it reads the company's reported financials and its last four earnings-call transcripts on demand. Run it with <code>python -m finn research ${esc(sym)}</code>, or connect the live API (see README).</p>` : ""}</div></div>`;
}

function credibilityHero(d) {
  const s = d.synthesis;
  const led = d.guidance.ledger;
  if (!s) {
    const calls = d.guidance.calls.length;
    const why = !calls ? "This company doesn't publish earnings-call transcripts, so there are no promises to track. The numbers below are still fully analysed."
      : d.guidance.pending ? `${d.guidance.pending} transcript${d.guidance.pending > 1 ? "s are" : " is"} queued for reading.` : "Not enough checkable guidance in the last four calls.";
    return `<div class="card soft"><div class="eyebrow">Promises vs delivery</div><p class="body" style="margin:6px 0 0">${esc(why)}</p></div>`;
  }
  const counts = {};
  led.forEach((g) => { const v = g.verdict || "pending"; counts[v] = (counts[v] || 0) + 1; });
  const tone = { high: "pos", medium: "amber", low: "neg" }[s.credibility.label] || "";
  return `<div class="card soft">
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:12px">
      <div><div class="eyebrow">Management credibility</div><div class="hero"><span class="big num">${s.credibility.score}</span><span class="muted" style="font-weight:700"> / 100</span></div></div>
      <span class="pill ${tone}" style="margin-bottom:6px">${esc(s.credibility.label)}</span>
    </div>
    <p class="body" style="margin:8px 0 0">${esc(s.credibility.summary)}</p>
    ${s.stale_as_of ? `<p class="note" style="margin:6px 0 0">Judgement from ${esc(new Date(s.stale_as_of).toLocaleDateString("en-IN", { day: "numeric", month: "short" }))}; new filings since then are queued for the model.</p>` : ""}
    ${stack(Object.entries(STATUS).map(([k, [lab]]) => ({ k: lab, v: counts[k] || 0, c: STATUS_COLOR[k] })))}
    <a class="link small" data-tab="promises" href="javascript:void 0">See all ${led.length} promises →</a>
  </div>`;
}

function overviewTab(d, ctx) {
  const s = d.synthesis;
  const seg = s?.business?.segments?.length ? `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">${s.business.segments.map((x) => `<span class="pill">${esc(x.name)}${x.share_pct != null ? ` · ${num(x.share_pct, 0)}%` : ""}</span>`).join("")}</div>` : "";
  const stmts = d.statements.map((x) => `<div class="flag"><span class="dot ${x.dir === "up" ? "green" : x.dir === "down" ? "red" : ""}"></span><span>${esc(x.text)}</span></div>`).join("");
  const flags = d.flags.map((f) => `<div class="flag"><span class="dot ${f.level}"></span><span>${esc(f.text)}</span></div>`).join("");
  const bb = s ? `<div class="bb">
      <div class="card"><div class="h2 pos">Bull case</div><ul>${s.bull.map((b) => `<li>${esc(b.point)}</li>`).join("")}</ul></div>
      <div class="card"><div class="h2 neg">Bear case</div><ul>${s.bear.map((b) => `<li>${esc(b.point)}</li>`).join("")}</ul></div></div>` : "";
  const nvn = s?.narrative_vs_numbers?.length ? `<section class="section"><div class="section-head"><h2 class="h2">Narrative vs numbers</h2></div>
      <div class="list">${s.narrative_vs_numbers.map((x) => `<div class="promise"><span class="pill ${x.verdict === "agrees" ? "pos" : x.verdict === "diverges" ? "neg" : ""}">${x.verdict === "agrees" ? "Story holds" : x.verdict === "diverges" ? "Diverges" : "Too early"}</span>
        <div class="stmt">${esc(x.claim)}</div><div class="evidence">${esc(x.reality)}</div></div>`).join("")}</div></section>` : "";
  const qs = s?.questions?.length ? `<section class="section"><div class="section-head"><h2 class="h2">Ask next</h2></div><div class="card soft">${s.questions.map((q, i) => `<div class="flag"><span class="pill blue">${i + 1}</span><span>${esc(q)}</span></div>`).join("")}</div></section>` : "";
  return `
    <section class="section" style="margin-top:18px"><div class="section-head"><h2 class="h2">The business</h2></div>
      <p class="body" style="margin:0">${esc(s?.business?.what_it_does || d.about)}</p>${seg}</section>
    <section class="section"><div class="section-head"><h2 class="h2">What's changing</h2></div><div class="card">${stmts || '<span class="muted">Not enough history.</span>'}</div></section>
    ${flags ? `<section class="section"><div class="section-head"><h2 class="h2">Flags</h2></div><div class="card">${flags}</div></section>` : ""}
    ${nvn}
    ${bb ? `<section class="section"><div class="section-head"><h2 class="h2">Bull vs bear</h2></div>${bb}</section>` : ""}
    ${qs}`;
}

function promisesTab(d) {
  const g = d.guidance;
  if (!g.ledger.length) return `<div class="empty"><div class="h2">No promises to show</div><p>${g.calls.length ? "Transcripts are queued for reading, or the calls carried no checkable guidance." : "The company doesn't publish concall transcripts."}</p></div>`;
  const drift = g.drift.map((x) => `<div class="promise"><div style="display:flex;justify-content:space-between;align-items:center"><b>${esc(METRIC[x.metric] || x.metric)} · ${esc(x.horizon)}</b>
      <span class="pill ${x.move === "held" ? "" : (x.move === "raised") !== !!x.lower_is_better ? "pos" : "neg"}">${{ raised: "Raised", lowered: "Lowered", cut: "Lowered", held: "Held" }[x.move] || x.move}</span></div>
      <div class="path" style="margin-top:6px">${x.sequence.map((s) => `<span class="node">${num(s.low, 1)}${s.high !== s.low ? `–${num(s.high, 1)}` : ""}${x.unit && x.unit !== "%" ? "" : "%"}</span><span class="muted tiny">${esc(s.call)}</span>`).join('<span class="edge">→</span>')}</div></div>`).join("");
  const item = (x, showCall = false) => {
    const [lab, cls] = STATUS[x.verdict || "pending"] || STATUS.pending;
    const actual = x.check ? `${x.check.basis}: <b class="num">${num(x.check.actual, 1)}${(x.unit || "").includes("%") ? "%" : ""}</b>` : (x.actual_text || "");
    return `<div class="promise"><div style="display:flex;justify-content:space-between;gap:8px"><span class="pill">${esc(METRIC[x.metric] || x.metric)} · ${esc(x.horizon)}${showCall ? ` · said ${esc(x.call)}` : ""}</span><span class="pill ${cls}">${lab}</span></div>
      <div class="stmt">${esc(x.statement)}</div>
      ${actual ? `<div class="evidence small">${actual}</div>` : ""}
      ${x.evidence ? `<div class="small" style="margin-top:4px;color:var(--ink-2)">${esc(x.evidence)}</div>` : ""}
      <details><summary class="tiny link" style="margin-top:6px">Quote &amp; source</summary>
      <div class="quote">“${esc(x.quote)}”<br><span class="tiny muted">${esc(x.speaker || "Management")} · <a class="link tiny" href="${esc(x.doc_url)}" target="_blank" rel="noopener">transcript p.${x.page ?? "?"} ${ICON.ext}</a></span></div></details></div>`;
  };
  // Lead with what a PM should read first: the decided, consequential promises.
  const decided = (x) => ["delivered", "missed", "walked_back", "at_risk", "on_track"].includes(x.verdict);
  const head = [...g.ledger].sort((a, b) => (decided(b) - decided(a)) || ((b.priority || 0) - (a.priority || 0))).slice(0, 8);
  const headIds = new Set(head.map((x) => x.id));
  const byCall = {};
  g.ledger.filter((x) => !headIds.has(x.id)).forEach((x) => { (byCall[x.call] = byCall[x.call] || []).push(x); });
  const calls = Object.keys(byCall).sort((a, b) => byCall[b][0].call_end.localeCompare(byCall[a][0].call_end));
  const tone = Object.fromEntries((g.tones || []).map((t) => [t.call, t]));
  const tones = (g.tones || []).filter((t) => t.label).map((t) => `<span class="pill" title="${esc(t.why || "")}">${esc(t.call)}: ${esc(t.label)}</span>`).join(" ");
  const ledger = `<section class="section"><div class="section-head"><h2 class="h2">Headline promises</h2><span class="count">${head.length} of ${g.ledger.length}</span></div>
      <div class="list">${head.map((x) => item(x, true)).join("")}</div>
      ${tones ? `<div class="why" style="margin-top:10px"><span class="tiny muted" style="align-self:center">Tone by call</span> ${tones}</div>` : ""}</section>
    ${calls.length ? `<section class="section"><details><summary class="section-head"><h2 class="h2">Every other promise</h2><span class="link">${g.ledger.length - head.length} more</span></summary>
      ${calls.map((c) => `<div class="eyebrow" style="margin:14px 0 6px">${esc(c)} call${tone[c]?.label ? ` · tone ${esc(tone[c].label)}` : ""}</div><div class="list">${byCall[c].map((x) => item(x)).join("")}</div>`).join("")}</details></section>` : ""}`;
  const read = g.calls.filter((c) => c.status === "analysed");
  const sent = read.reduce((a, c) => a + (c.chars_sent || 0), 0), tot = read.reduce((a, c) => a + (c.chars_total || 0), 0);
  const dropped = read.reduce((a, c) => a + (c.dropped_unverified || 0), 0);
  return `${drift ? `<section class="section" style="margin-top:18px"><div class="section-head"><h2 class="h2">Guidance drift</h2></div><div class="list">${drift}</div></section>` : ""}
    ${ledger}
    <p class="note" style="margin-top:18px">Read ${read.length} transcript${read.length === 1 ? "" : "s"}; ${tot ? Math.round((sent / tot) * 100) : 0}% of the text reached the model after retrieval. Every quote is machine-checked against the transcript — ${dropped} paraphrased quote${dropped === 1 ? " was" : "s were"} dropped. Status is computed from reported numbers where the promise is numeric.</p>`;
}

function numbersTab(d) {
  const q = d.quarters.slice(-12), y = d.years.slice(-10);
  const lender = d.kind === "lender";
  const t = d.ttm || {};
  const tr = d.trajectory || {};
  const k = (label, v, sub = "", cls = "") => `<div class="kpi"><div class="k">${label}</div><div class="v">${v}</div>${sub ? `<div class="d ${cls}">${sub}</div>` : ""}</div>`;
  return `<section class="section" style="margin-top:18px"><div class="kpis">
      ${k("TTM revenue", inr(t.revenue, "cr"), tr.rev_cagr_3y != null ? `${pct(tr.rev_cagr_3y, 0)} 3y CAGR` : "", signCls(tr.rev_cagr_3y))}
      ${k(lender ? "PBT margin" : "EBITDA margin", t.margin != null ? `${num(t.margin, 1)}%` : "—", tr.margin_change_3y_bps != null && !lender ? `${tr.margin_change_3y_bps >= 0 ? "+" : "−"}${Math.abs(tr.margin_change_3y_bps)} bps 3y` : "", signCls(tr.margin_change_3y_bps))}
      ${k("TTM PAT", inr(t.pat, "cr"), tr.pat_cagr_3y != null ? `${pct(tr.pat_cagr_3y, 0)} 3y CAGR` : "", signCls(tr.pat_cagr_3y))}
      ${k("ROCE", esc(d.quote.roce || "—"))}${k("ROE", esc(d.quote.roe || "—"))}${k("P/E", esc(d.quote.pe || "—"))}
    </div></section>
    <section class="section"><div class="section-head"><h2 class="h2">Last 12 quarters</h2><span class="tiny muted">bars: revenue · line: ${lender ? "pre-tax" : "EBITDA"} margin</span></div>
      <div class="card">${bars({ labels: q.map((x) => x.label.replace(" FY", "·")), series: [{ name: "Revenue", values: q.map((x) => x.revenue), color: "var(--ink)" }], line: { name: "Margin", values: q.map((x) => x.margin), color: "var(--accent)" }, fmt: (v) => inr(v), lineFmt: (v) => `${v.toFixed(0)}%` })}
      <table class="rtable"><thead><tr><th>Quarter</th><th>Revenue</th><th>YoY</th><th>PAT YoY</th></tr></thead><tbody>
      ${q.slice(-5).reverse().map((x) => `<tr><td>${esc(x.label)}</td><td class="v">${inr(x.revenue, "")}</td><td class="${signCls(x.rev_yoy)}">${pct(x.rev_yoy, 0)}</td><td class="${signCls(x.pat_yoy)}">${pct(x.pat_yoy, 0)}</td></tr>`).join("")}</tbody></table></div></section>
    <section class="section"><div class="section-head"><h2 class="h2">The long view</h2><span class="tiny muted">revenue vs profit after tax, ₹ cr</span></div>
      <div class="card">${bars({ labels: y.map((x) => x.fy), series: [{ name: "Revenue", values: y.map((x) => x.revenue), color: "#c9ced6" }, { name: "PAT", values: y.map((x) => x.pat), color: "var(--ink)" }], fmt: (v) => inr(v) })}</div></section>`;
}

function balanceTab(d) {
  const b = d.balance;
  const rows = b.rows.filter((r) => /^FY/.test(r.label)).slice(-8);
  const lender = d.kind === "lender";
  const f = b.funding;
  const wc = b.wc.filter((x) => x.debtor != null || x.ccc != null).slice(-6);
  const q = d.quarters.slice(-8);
  return `<section class="section" style="margin-top:18px"><div class="section-head"><h2 class="h2">${lender ? "Borrowings vs equity" : "Debt / equity"}</h2></div>
      <div class="card">${bars({ labels: rows.map((r) => r.label), series: [{ name: "D/E", values: rows.map((r) => r.de), color: "var(--ink)" }], fmt: (v) => `${v.toFixed(2)}x` })}</div></section>
    ${f ? `<section class="section"><div class="section-head"><h2 class="h2">How it's funded</h2><span class="tiny muted">latest balance sheet</span></div><div class="card">${stack([
      { k: "Equity", v: f.equity, c: "var(--ink)" }, { k: "Deposits", v: f.deposits, c: "var(--accent)" }, { k: "Debt", v: f.debt, c: "#e0a100" }, { k: "Other liabilities", v: f.other, c: "#c9ced6" }])}</div></section>` : ""}
    ${wc.length ? `<section class="section"><div class="section-head"><h2 class="h2">Working-capital cycle</h2><span class="tiny muted">days</span></div><div class="card">
      <table class="rtable"><thead><tr><th>Year</th><th>Debtors</th><th>Inventory</th><th>Payables</th><th>Cycle</th></tr></thead><tbody>
      ${wc.map((x) => `<tr><td>${esc(x.fy)}</td><td>${num(x.debtor)}</td><td>${num(x.inventory)}</td><td>${num(x.payable)}</td><td class="v">${num(x.ccc)}</td></tr>`).join("")}</tbody></table></div></section>` : ""}
    ${lender && q.some((x) => x.gnpa != null) ? `<section class="section"><div class="section-head"><h2 class="h2">Asset quality</h2><span class="tiny muted">gross NPA %</span></div>
      <div class="card">${bars({ labels: q.map((x) => x.label.replace(" FY", "·")), series: [{ name: "GNPA", values: q.map((x) => x.gnpa), color: "#e0a100" }], fmt: (v) => `${v.toFixed(2)}%` })}</div></section>` : ""}`;
}

function cashTab(d) {
  const c = d.cash;
  if (c.note) return `<div class="card soft" style="margin-top:18px"><p class="body" style="margin:0">${esc(c.note)}</p></div>`;
  const rows = c.rows.slice(-8);
  return `<section class="section" style="margin-top:18px"><div class="kpis">
      <div class="kpi"><div class="k">5-yr CFO / PAT</div><div class="v ${c.cfo_pat_5y != null && c.cfo_pat_5y < 0.7 ? "neg" : ""}">${c.cfo_pat_5y != null ? `${num(c.cfo_pat_5y, 2)}x` : "—"}</div></div>
      <div class="kpi"><div class="k">5-yr free cash</div><div class="v ${signCls(c.fcf_5y)}">${inr(c.fcf_5y)}</div></div>
      <div class="kpi"><div class="k">Last yr capex</div><div class="v">${inr(rows[rows.length - 1]?.capex)}</div></div></div></section>
    <section class="section"><div class="section-head"><h2 class="h2">Do profits turn into cash?</h2><span class="tiny muted">operating cash vs PAT, ₹ cr</span></div>
      <div class="card">${bars({ labels: rows.map((r) => r.fy), series: [{ name: "PAT", values: rows.map((r) => r.pat), color: "#c9ced6" }, { name: "Operating cash", values: rows.map((r) => r.cfo), color: "var(--ink)" }], fmt: (v) => inr(v) })}</div></section>
    <section class="section"><div class="section-head"><h2 class="h2">Free cash flow</h2><span class="tiny muted">operating cash − capex</span></div>
      <div class="card">${bars({ labels: rows.map((r) => r.fy), series: [{ name: "FCF", values: rows.map((r) => r.fcf), color: "var(--accent)" }], fmt: (v) => inr(v) })}</div></section>`;
}

function peopleTab(d, ctx) {
  const sym = d.symbol;
  const evs = ctx.data.events.filter((e) => e.symbol === sym);
  const mg = evs.filter((e) => e.category === "management_change");
  const fake = { symbol: sym, title: "", summary_src: "", brief: null };
  const all = ctx.net ? ctx.net.people.filter((p) => p.career.some((c) => c.org_id === sym)) : [];
  return `<section class="section" style="margin-top:18px">${whoToCallBlock(fake, ctx, 5, `Who to call about ${shortCo(d.name)}`) || '<div class="card soft">Nobody in your network has worked here, at a direct peer, or in this sector.</div>'}</section>
    ${all.length ? `<section class="section"><div class="section-head"><h2 class="h2">Worked here</h2></div><div class="list">${all.map((p) => {
      const st = p.career.find((c) => c.org_id === sym);
      return `<a class="row" href="#/p/${p.id}"><span class="avatar">${initials(p.name)}</span><span class="grow"><div class="title">${esc(p.name)}</div><div class="meta">${esc(st.role)} · ${st.start}–${st.end ?? "now"}</div></span></a>`;
    }).join("")}</div></section>` : ""}
    ${mg.length ? `<section class="section"><div class="section-head"><h2 class="h2">Management changes</h2></div><div class="list">${mg.map((e) => eventRow(e, ctx)).join("")}</div></section>` : ""}`;
}

const TABS = [["overview", "Overview"], ["promises", "Promises"], ["numbers", "Numbers"], ["balance", "Balance sheet"], ["cash", "Cash"], ["people", "People"]];

export function renderCompany(d, ctx, tab = "overview") {
  const price = d.quote.price;
  const sp = d.quote.spark.map((x) => x[1]);
  const chg = sp.length > 1 ? (sp[sp.length - 1] / sp[0] - 1) * 100 : null;
  const evs = ctx.data.events.filter((e) => e.symbol === d.symbol && e.tier !== "routine").slice(0, 3);
  const body = { overview: overviewTab, promises: promisesTab, numbers: numbersTab, balance: balanceTab, cash: cashTab, people: peopleTab }[tab](d, ctx);
  return `<div class="view">
    <a class="back" href="#/research">${ICON.back} Research</a>
    <header class="top" style="padding-top:6px">
      <div class="co"><span class="logo" style="width:44px;height:44px;border-radius:13px">${logoText(d.symbol)}</span>
        <span><div class="h1" style="margin:0">${esc(shortCo(d.name))}</div><div class="small muted">${esc(d.symbol)} · ${esc((d.sector_path || []).slice(1, 3).join(" › "))}</div></span></div>
      <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-top:14px">
        <div><div style="font-size:28px;font-weight:800;letter-spacing:-0.03em" class="num">${esc(price || "—")}</div>
          <div class="small muted">${esc(d.quote.market_cap || "")} mkt cap${chg != null ? ` · <span class="${signCls(chg)}">${pct(chg)} 6m</span>` : ""}</div></div>
        ${spark(sp, { w: 120, h: 40 })}
      </div>
    </header>
    ${credibilityHero(d)}
    ${evs.length && tab === "overview" ? `<div class="list" style="margin-bottom:6px">${evs.map((e) => eventRow(e, ctx)).join("")}</div>` : ""}
    <nav class="seg">${TABS.map(([k, l]) => `<button data-tab="${k}" class="${k === tab ? "on" : ""}">${l}</button>`).join("")}</nav>
    ${body}
    <p class="note" style="margin-top:24px">Sources: ${d.sources.map(esc).join(" · ")}. Basis: ${esc(d.basis || "")}. Built ${esc(new Date(d.generated_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }))}.
      ${d.documents.transcripts.length ? `Transcripts: ${d.documents.transcripts.slice(0, 4).map((t) => `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.month)}</a>`).join(", ")}.` : ""}</p>
  </div>`;
}
