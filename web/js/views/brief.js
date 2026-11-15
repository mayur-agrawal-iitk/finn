import { eventCard, eventRow, headline, shortCo } from "../cards.js";
import { esc, initials, logoText, num, pct, signCls, spark } from "../lib.js";
import { CATEGORY_LABEL, eodAlerts, explainMove, WINDOWS, windowStart } from "../rules.js";

function greeting(now) {
  const h = now.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function marketState(now) {
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const d = ist.getDay(), m = ist.getHours() * 60 + ist.getMinutes();
  if (d === 0 || d === 6) return "Markets closed";
  if (m < 555) return "Pre-open";
  if (m <= 930) return "Market open";
  return "Markets closed";
}

export function renderBrief(ctx) {
  const { prefs, data } = ctx;
  const since = windowStart(prefs, ctx.now);
  const inWin = data.events.filter((e) => new Date(e.dt) >= since && !prefs.dismissed.includes(e.id));
  const scored = inWin.map((e) => ({ e, s: ctx.scored[e.id] }));
  const material = scored.filter((x) => x.s.tier === "material").sort((a, b) => b.s.score - a.s.score).map((x) => x.e);
  const notable = scored.filter((x) => x.s.tier === "notable").sort((a, b) => b.s.score - a.s.score).map((x) => x.e);
  const routine = scored.filter((x) => x.s.tier === "routine").map((x) => x.e);
  const alerts = eodAlerts(data.eod, ctx.symbols, prefs, since);
  const nudges = ctx.net ? ctx.net.nudges(data.events.map((e) => ({ ...e, headline: headline(e) }))) : [];
  const holdings = new Set(inWin.map((e) => e.symbol));

  const w = WINDOWS.find((x) => x.id === prefs.window);
  const chips = WINDOWS.map((x) => `<button class="chip ${x.id === prefs.window ? "on" : ""}" data-window="${x.id}">${x.label}</button>`).join("");

  let hero;
  if (material.length) {
    hero = `<div class="h-display">${material.length} thing${material.length > 1 ? "s" : ""} need${material.length > 1 ? "" : "s"} you</div>
      <div class="sub">${inWin.length} filing${inWin.length === 1 ? "" : "s"} across ${holdings.size} holding${holdings.size === 1 ? "" : "s"} in the last ${w.label}${routine.length ? ` · ${routine.length} routine tucked away` : ""}${alerts.length ? ` · ${alerts.length} unusual move${alerts.length > 1 ? "s" : ""}` : ""}</div>`;
  } else {
    const wider = WINDOWS[WINDOWS.findIndex((x) => x.id === prefs.window) + 1];
    hero = `<div class="h-display">Quiet ${w.label}</div>
      <div class="sub">${inWin.length ? `${inWin.length} filing${inWin.length > 1 ? "s" : ""}, none material.` : "No filings across your holdings."}${alerts.length ? ` ${alerts.length} unusual move${alerts.length > 1 ? "s" : ""} below.` : ""}</div>
      ${wider ? `<button class="chip ghost" style="margin-top:12px" data-window="${wider.id}">See the last ${wider.label} →</button>` : ""}`;
  }

  const alertRows = alerts.slice(0, 6).map((a) => {
    const why = explainMove(a, data.events);
    const hits = [a.hitMove ? `${pct(a.ret)}${prefs.relative_to_index && a.iret !== null ? ` (${pct(a.move)} vs Nifty)` : ""}` : null, a.hitVol ? `${num(a.vm, 1)}× avg volume` : null].filter(Boolean).join(" · ");
    return `<a class="row" href="#/r/${a.symbol}">
      <span class="logo">${logoText(a.symbol)}</span>
      <span class="grow"><div class="title">${esc(shortCo(ctx.names[a.symbol] || a.symbol))} <span class="${signCls(a.ret)} num">${pct(a.ret)}</span></div>
      <div class="meta">${new Date(a.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })} · ${hits}</div>
      <div class="meta" style="white-space:normal;color:${why ? "var(--ink-2)" : "var(--amber)"}">${why ? `Likely trigger: ${esc(headline(why))}` : "No filing explains this move — worth a call."}</div></span>
      <span class="right">${spark(a.series)}</span></a>`;
  }).join("");

  const routineGroups = {};
  routine.forEach((e) => { const k = CATEGORY_LABEL[e.category] || e.category; routineGroups[k] = (routineGroups[k] || 0) + 1; });
  const routineSummary = Object.entries(routineGroups).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${k.toLowerCase()}`).join(" · ");

  const nudgeCards = nudges.map((n) => `<a class="card soft tap" href="#/p/${n.person.id}" style="display:block">
      <div class="co"><span class="avatar" style="background:#fff">${initials(n.person.name)}</span>
      <span><div style="font-weight:700">${esc(n.person.name)}</div><div class="tiny muted">Last spoke ${Math.round(n.tie.months)} months ago · your ${esc(n.tie.rel)}</div></span></div>
      <p class="body" style="margin:10px 0 0">${esc(n.text)}</p>
      <div class="link" style="margin-top:8px">A natural reason to reconnect →</div></a>`).join("");

  return `<div class="view">
    <header class="top">
      <div class="top-row"><span class="brand">FINN<b>.</b></span><span class="tiny muted">${esc(marketState(ctx.now))} · data ${new Date(data.meta.generated_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</span></div>
      <div class="eyebrow" style="margin-top:18px">${greeting(new Date())} · ${ctx.now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</div>
      ${hero}
      <div class="chips" style="margin-top:14px">${chips}</div>
    </header>

    ${material.length ? `<section class="section"><div class="section-head"><h2 class="h2">Needs you</h2><span class="count">${material.length}</span></div>
      ${material.map((e) => eventCard(e, ctx)).join("")}</section>` : ""}

    ${alerts.length ? `<section class="section"><div class="section-head"><h2 class="h2">Unusual moves</h2><a class="link" href="#/watch">Rules: ±${prefs.price_move_pct}% · ${prefs.volume_multiple}× vol</a></div>
      <div class="list">${alertRows}</div></section>` : ""}

    ${notable.length ? `<section class="section"><div class="section-head"><h2 class="h2">Worth a glance</h2><span class="count">${notable.length}</span></div>
      <div class="list">${notable.map((e) => eventRow(e, ctx)).join("")}</div></section>` : ""}

    ${routine.length ? `<section class="section"><details><summary class="section-head"><h2 class="h2">Routine <span class="count">${routine.length}</span></h2><span class="link">Show</span></summary>
      <p class="small muted" style="margin:-4px 0 10px">${esc(routineSummary)}</p>
      <div class="list">${routine.map((e) => eventRow(e, ctx)).join("")}</div></details></section>` : ""}

    ${nudges.length ? `<section class="section"><div class="section-head"><h2 class="h2">Reconnect</h2><a class="link" href="#/network">Network</a></div>${nudgeCards}</section>` : ""}

    <p class="note" style="margin-top:28px">Ranked by what could move the stock (results, management, deals, legal), sized by your position and your categories. Filings: BSE/NSE. Prices: end-of-day. <a href="#/watch">Change what counts →</a></p>
  </div>`;
}
