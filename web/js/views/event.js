import { cleanTitle, headline, netPathsBlock, personBlock, resultsTable, shortCo, whoToCallBlock } from "../cards.js";
import { esc, ICON, logoText, pct, signCls } from "../lib.js";
import { CATEGORY_LABEL } from "../rules.js";

export function renderEvent(id, ctx) {
  const e = ctx.data.events.find((x) => x.id === id);
  if (!e) return `<div class="view"><a class="back" href="#/brief">${ICON.back} Brief</a><div class="empty">This filing has rolled out of the window.</div></div>`;
  const s = ctx.scored[e.id] || e;
  const b = e.brief;
  const people = (e.people || []).map((p) => `<div class="card">${personBlock(p, ctx, { full: true })}${p.change === "appointed" ? netPathsBlock(p, ctx, 3) : ""}</div>`).join("");
  const keyNums = b?.key_numbers?.length ? `<div class="kpis">${b.key_numbers.slice(0, 6).map((k) => `<div class="kpi"><div class="k">${esc(k.label)}</div><div class="v" style="font-size:15px">${esc(k.value)}</div></div>`).join("")}</div>` : "";
  const qs = b?.questions?.length ? `<section class="section"><div class="section-head"><h2 class="h2">Ask them</h2></div><div class="card soft">${b.questions.map((q, i) => `<div class="flag"><span class="pill blue">${i + 1}</span><span>${esc(q)}</span></div>`).join("")}</div></section>` : "";
  const rx = e.reaction ? `<span class="pill ${signCls(e.reaction.abn ?? e.reaction.ret)}">${pct(e.reaction.ret)} on ${new Date(e.reaction.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}${e.reaction.abn != null ? ` · ${pct(e.reaction.abn)} vs Nifty` : ""}</span>` : "";
  const related = (e.related || []).map((r) => `<a class="row" href="${esc(r.url || "#")}" target="_blank" rel="noopener"><span class="grow"><div class="title">${esc(cleanTitle(r.title))}</div><div class="meta">${esc(r.source)}</div></span>${ICON.ext}</a>`).join("");
  return `<div class="view">
    <a class="back" href="javascript:history.back()">${ICON.back} Back</a>
    <header class="top" style="padding-top:4px">
      <a class="co" href="#/r/${e.symbol}"><span class="logo">${logoText(e.symbol)}</span><span><div class="co-name">${esc(shortCo(e.company))}</div><div class="co-sym">${esc(CATEGORY_LABEL[e.category] || e.category)} · ${new Date(e.dt).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</div></span></a>
      <div class="h1" style="margin-top:14px">${esc(headline(e))}</div>
      ${b?.so_what ? `<p class="body" style="margin:6px 0 0">${esc(b.so_what)}</p>` : e.summary_src ? `<p class="body" style="margin:6px 0 0">${esc(e.summary_src)}</p>` : ""}
      <div class="why">${rx}${e.facts?.amount_cr ? `<span class="pill">₹${Math.round(e.facts.amount_cr).toLocaleString("en-IN")} cr${e.facts.pct_of_ttm_revenue != null ? ` · ${e.facts.pct_of_ttm_revenue}% of TTM revenue` : ""}</span>` : ""}</div>
    </header>
    ${e.category === "results" && e.results ? `<div class="card">${resultsTable(e.results)}</div>` : ""}
    ${keyNums}
    ${people ? `<section class="section"><div class="section-head"><h2 class="h2">People in this filing</h2></div>${people}</section>` : ""}
    <section class="section">${whoToCallBlock(e, ctx, 4, "Who in your network can explain it") || ""}</section>
    ${qs}
    <section class="section"><div class="section-head"><h2 class="h2">Why FINN ranked it here</h2></div>
      <div class="card soft small"><dl class="kv">
        <dt>Category</dt><dd>${esc(CATEGORY_LABEL[e.category] || e.category)}${e.subtype && !["unknown", "routine"].includes(e.subtype) ? ` · ${esc(e.subtype.replace(/_/g, " "))}` : ""}${e.facts?.also?.length ? ` (also: ${e.facts.also.map((c) => CATEGORY_LABEL[c] || c).join(", ")})` : ""}</dd>
        <dt>How</dt><dd>${e.method === "rule" ? "Exchange subject matched a rule" : e.method === "rule:summary" ? "Generic subject — rule matched the filing summary" : esc(e.method)}</dd>
        <dt>Could move the stock</dt><dd>${e.score}/100</dd>
        <dt>For you</dt><dd>${Math.round(s.score)}/100 · ${esc(s.tier)}</dd>
        <dt>Because</dt><dd>${(s.reasons || []).map(esc).join(" · ")}</dd>
        <dt>Source</dt><dd>${esc(e.source)}</dd></dl></div></section>
    <section class="section"><div class="list">
      ${e.url ? `<a class="row" href="${esc(e.url)}" target="_blank" rel="noopener"><span class="grow"><div class="title">Read the filing</div><div class="meta">${esc(cleanTitle(e.title))}</div></span>${ICON.ext}</a>` : ""}
      ${related}
      <a class="row" href="#/r/${e.symbol}"><span class="grow"><div class="title">Research ${esc(shortCo(e.company))}</div><div class="meta">Promises vs delivery, numbers, balance sheet, cash</div></span>›</a>
    </div></section>
  </div>`;
}
