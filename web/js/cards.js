// Event cards: the unit of the Brief. Each answers: what happened, why it's here, who can explain it.
import { CATEGORY_LABEL } from "./rules.js";
import { ago, esc, ICON, initials, inr, logoText, pct, signCls, yrs } from "./lib.js";

export function cleanTitle(t) {
  return String(t || "")
    .replace(/^Announcement under Regulation 30 \(LODR\)\s*-\s*/i, "")
    .replace(/^(Disclosure|Intimation|Announcement) Under Regulation 30.*?(-|–)\s*/i, "")
    .replace(/_/g, " ").trim();
}

function shortCo(name) {
  return String(name || "").replace(/ (Ltd|Limited)\.?$/i, "").replace(/ India$/i, "");
}

export function headline(e) {
  if (e.category === "results" && e.results?.pending) return `${e.results.quarter} results filed`;
  if (e.category === "results" && e.results && !e.results.pending) {
    const by = Object.fromEntries(e.results.rows.map((r) => [r.key, r]));
    const parts = [];
    if (by.revenue?.yoy != null) parts.push(`revenue ${pct(by.revenue.yoy, 0)}`);
    if (by.pat?.yoy != null) parts.push(`PAT ${pct(by.pat.yoy, 0)}`);
    return `${e.results.quarter}: ${parts.join(", ")} YoY`;
  }
  if (e.category === "management_change" && e.people?.length) {
    const p = e.people.find((x) => x.is_kmp && x.change === "appointed") || e.people.find((x) => x.change === "appointed") || e.people[0];
    const verb = { appointed: "New", resigned: "Exit:", retired: "Retiring:", reappointed: "Re-appointed:", redesignated: "New role:" }[p.change] || "";
    return verb === "New" ? `New ${p.role}: ${p.name}` : `${verb} ${p.name}, ${p.role}`;
  }
  if (e.brief?.one_line) return e.brief.one_line;
  if (e.summary_src && e.summary_src.length > 20 && !/has informed the exchange/i.test(e.summary_src)) return e.summary_src.replace(/\.$/, "");
  return cleanTitle(e.title);
}

const TIER_PILL = { material: '<span class="pill dark">Needs you</span>', notable: '<span class="pill">Worth a look</span>', routine: '<span class="pill">Routine</span>' };

export function resultsTable(r) {
  if (!r || r.pending) return `<p class="body small muted">${esc(r?.reason || "Headline numbers will appear once the standardised tables include this quarter.")}</p>`;
  const rows = r.rows.map((x) => `<tr><td>${esc(x.label)}</td><td class="v">${inr(x.cur, "")}</td><td class="${signCls(x.yoy)}">${pct(x.yoy, 0)}</td><td class="${signCls(x.qoq)}">${pct(x.qoq, 0)}</td></tr>`).join("");
  let margin = "";
  if (r.margin && r.margin.cur != null) {
    const dy = r.margin.yago != null ? (r.margin.cur - r.margin.yago) : null;
    margin = `<div class="small" style="margin-top:8px;color:var(--ink-2)">EBITDA margin <b class="num" style="color:var(--ink)">${r.margin.cur.toFixed(1)}%</b>${dy != null ? ` <span class="${signCls(dy)}">${dy >= 0 ? "+" : "−"}${Math.abs(dy * 100).toFixed(0)} bps YoY</span>` : ""}</div>`;
  }
  let npa = "";
  if (r.extra && r.extra["Gross NPA %"]) {
    const g = r.extra["Gross NPA %"];
    npa = `<div class="small" style="margin-top:4px;color:var(--ink-2)">Gross NPA <b class="num" style="color:var(--ink)">${g.cur}%</b> vs ${g.yago ?? "—"}% a year ago</div>`;
  }
  return `<table class="rtable"><thead><tr><th>${esc(r.quarter)} · ₹ cr</th><th>Value</th><th>YoY</th><th>QoQ</th></tr></thead><tbody>${rows}</tbody></table>${margin}${npa}
    ${r.note ? `<p class="note" style="margin:6px 0 0">${esc(r.note)}</p>` : ""}
    <p class="note" style="margin:6px 0 0">${r.basis ? esc(r.basis[0].toUpperCase() + r.basis.slice(1)) + " · " : ""}${esc(r.source || "")}</p>`;
}

export function personBlock(p, ctx, { full = false } = {}) {
  if (ctx.net) p = ctx.net.richest(p);
  const career = (p.career || []).slice(0, full ? 8 : 4).map((c) => `<span class="pill" title="${esc(c.role || "")}">${esc(c.org)}${c.start_year || c.end_year ? ` · ${yrs(c.start_year, c.end_year)}` : ""}</span>`).join(" ");
  const edu = (p.education || []).map((ed) => `<span class="pill">${esc(ed.institution)}${ed.year ? ` · ${ed.year}` : ""}</span>`).join(" ");
  return `<div style="margin-top:10px">
    <div style="font-weight:700">${esc(p.name)} <span class="muted small">· ${esc(p.role)}${p.age ? ` · ${p.age}` : ""}</span></div>
    ${p.bio ? `<p class="body" style="margin:4px 0 6px">${esc(p.bio)}</p>` : ""}
    <div style="display:flex;flex-wrap:wrap;gap:6px">${career}${edu}</div>
  </div>`;
}

function netPathsBlock(person, ctx, n = 2) {
  if (!ctx.net) return "";
  const { paths, total, you } = ctx.net.pathsTo(person, n);
  if (!paths.length && !you) {
    return `<div class="net"><div class="net-title">Your network</div><div class="net-why">No one in your network overlaps with ${esc(person.name.split(" ")[0])} on employers or schools in the filing.</div></div>`;
  }
  const rows = paths.map((x) => `<a class="net-person" href="#/p/${x.person.id}">
      <span class="avatar">${initials(x.person.name)}</span>
      <span><span class="net-name">${esc(x.person.name)}</span>${ctx.net.bars(x.score / 0.75)}<span class="muted small"> · your ${esc(x.tie.rel)}</span>
      <div class="net-why">${esc(x.link.text)}</div></span></a>`).join("");
  const mine = you ? `<div class="net-why" style="margin-top:6px">And you: ${esc(you.text.replace(/^You was/, "You were").replace(/^You and/, "You and"))}</div>` : "";
  return `<div class="net"><div class="net-title">Who can get you to ${esc(person.name.split(" ").slice(-1)[0])}</div>${rows}${total > n ? `<div class="tiny muted" style="margin-top:4px">+${total - n} weaker path${total - n > 1 ? "s" : ""}</div>` : ""}${mine}</div>`;
}

export function whoToCallBlock(e, ctx, n = 2, title = "Best placed to explain") {
  if (!ctx.net) return "";
  const text = [e.title, e.summary_src, e.brief?.one_line, e.brief?.so_what].join(" ");
  const counterparties = ctx.net.orgsInText(text).filter((id) => id !== e.symbol);
  const ppl = ctx.net.whoToCall(e.symbol, { counterparties, topics: e.brief?.expertise_needed || [], n });
  if (!ppl.length) return "";
  const rows = ppl.map((x) => `<a class="net-person" href="#/p/${x.person.id}">
      <span class="avatar">${initials(x.person.name)}</span>
      <span><span class="net-name">${esc(x.person.name)}</span>${ctx.net.bars(x.tie.score)}<span class="muted small"> · your ${esc(x.tie.rel)}</span>
      <div class="net-why">${esc(x.text)}</div>
      ${x.insider ? `<div class="caution">Current employee of a listed company — keep it to public information (SEBI PIT rules).</div>` : ""}</span></a>`).join("");
  return `<div class="net"><div class="net-title">${esc(title)}</div>${rows}</div>`;
}

export function eventCard(e, ctx, { compact = false } = {}) {
  const pe = ctx.scored?.[e.id] || e;
  const why = (pe.reasons || []).slice(0, 4).map((r) => `<span class="pill">${esc(r)}</span>`).join("");
  let body = "";
  if (e.category === "results" && e.subtype === "filing") {
    body = resultsTable(e.results);
    const moves = (e.people || []).filter((p) => p.change !== "reappointed");
    if (moves.length) {
      body += `<div class="small" style="margin-top:10px;color:var(--ink-2)"><b style="color:var(--ink)">Also in this filing:</b> ${moves.slice(0, 3).map((p) => `${esc(p.name)} (${esc(p.role)}) ${p.change === "appointed" ? "appointed" : p.change === "resigned" || p.change === "retired" ? "leaves" : "moves on"}`).join("; ")}${moves.length > 3 ? ` and ${moves.length - 3} more` : ""}.</div>`;
    }
    if (e.results?.pending && e.brief?.one_line) body += `<p class="body small" style="margin:8px 0 0">${esc(e.brief.one_line)}</p>`;
  } else if (e.category === "management_change" && e.people?.length) {
    const lead = e.people.find((x) => x.is_kmp && x.change === "appointed") || e.people.find((x) => x.change === "appointed") || e.people[0];
    body = personBlock(lead, ctx) + (e.people.length > 1 ? `<p class="tiny muted" style="margin:8px 0 0">+${e.people.length - 1} other change${e.people.length > 2 ? "s" : ""} in this filing</p>` : "")
      + (compact ? "" : netPathsBlock(lead, ctx));
  } else {
    const sw = e.brief?.so_what || (e.facts?.pct_of_ttm_revenue != null ? `About ${e.facts.pct_of_ttm_revenue}% of trailing-12-month revenue.` : "");
    body = sw ? `<p class="body" style="margin:2px 0 0">${esc(sw)}</p>` : "";
  }
  const react = e.reaction && e.reaction.abn != null && Math.abs(e.reaction.abn) >= 2
    ? `<span class="pill ${signCls(e.reaction.abn)}">${pct(e.reaction.ret)} on ${new Date(e.reaction.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })} (${pct(e.reaction.abn)} vs Nifty)</span>` : "";
  const net = compact ? "" : (e.category === "management_change" && e.people?.length ? "" : (pe.tier === "material" || e.category === "litigation" || e.category === "M&A") ? whoToCallBlock(e, ctx) : "");
  return `<article class="card">
    <div class="card-top">
      <a class="co" href="#/r/${e.symbol}"><span class="logo">${logoText(e.symbol)}</span><span style="min-width:0"><div class="co-name">${esc(shortCo(e.company))}</div><div class="co-sym">${esc(CATEGORY_LABEL[e.category] || e.category)} · ${ago(e.dt, ctx.now)}</div></span></a>
      ${TIER_PILL[pe.tier] || ""}
    </div>
    <a href="#/e/${e.id}"><div class="headline">${esc(headline(e))}</div></a>
    ${body}
    ${react ? `<div class="why">${react}</div>` : ""}
    ${net}
    ${compact ? "" : `<div class="why">${why}</div>`}
    <div class="actions">
      <a class="primary" href="#/e/${e.id}">Details</a>
      ${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">Filing ${ICON.ext}</a>` : ""}
      <a href="#/r/${e.symbol}">Research</a>
      <button data-dismiss="${e.id}" style="margin-left:auto">Done</button>
    </div>
  </article>`;
}

export function eventRow(e, ctx) {
  return `<a class="row" href="#/e/${e.id}">
    <span class="logo">${logoText(e.symbol)}</span>
    <span class="grow"><div class="title">${esc(headline(e))}</div><div class="meta">${esc(shortCo(e.company))} · ${esc(CATEGORY_LABEL[e.category] || e.category)} · ${ago(e.dt, ctx.now)}</div></span>
  </a>`;
}

export { shortCo, netPathsBlock };
