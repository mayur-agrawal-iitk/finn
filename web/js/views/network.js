import { headline, shortCo } from "../cards.js";
import { esc, ICON, initials } from "../lib.js";
import { THEMES } from "../network.js";

function personRow(p, ctx, why = "") {
  const t = ctx.net.tie(p);
  return `<a class="row" href="#/p/${p.id}"><span class="avatar" style="background:var(--accent-soft)">${initials(p.name)}</span>
    <span class="grow"><div class="title">${esc(p.name)}${ctx.net.bars(t.score)}</div><div class="meta">${esc(why || p.headline)}</div></span></a>`;
}

/** Network answers for a free-text question: a person, a company, a theme or a public figure from a filing. */
export function answer(q, ctx) {
  const net = ctx.net;
  const s = q.trim();
  if (!s) return "";
  const out = [];
  // 1. a public person named in recent filings (e.g. an incoming CEO)
  const people = ctx.data.events.flatMap((e) => (e.people || []).map((p) => ({ p, e })));
  const found = people.find(({ p }) => p.name.toLowerCase().split(" ").some((w) => w.length > 3 && s.toLowerCase().includes(w)));
  const pub = found ? { ...found, p: net.richest(found.p) } : null;
  if (pub) {
    const { paths, total } = net.pathsTo(pub.p, 4);
    out.push(`<section class="section"><div class="section-head"><h2 class="h2">Paths to ${esc(pub.p.name)}</h2><span class="count">${total}</span></div>
      <p class="small muted" style="margin:-4px 0 8px">${esc(pub.p.role)}, ${esc(shortCo(pub.e.company))} · from the ${new Date(pub.e.dt).toLocaleDateString("en-IN", { day: "numeric", month: "short" })} filing</p>
      <div class="list">${paths.map((x) => `<a class="row" href="#/p/${x.person.id}" style="align-items:flex-start"><span class="avatar" style="background:var(--accent-soft)">${initials(x.person.name)}</span>
        <span class="grow"><div class="path"><span class="node">You</span><span class="edge">— ${esc(x.tie.rel)} —</span><span class="node">${esc(x.person.name)}</span><span class="edge">— ${esc(x.link.kind === "studied" ? "studied" : "worked")} —</span><span class="node">${esc(pub.p.name)}</span></div>
        <div class="meta" style="white-space:normal">${esc(x.link.text)}</div></span></a>`).join("") || '<div class="empty">No overlap found.</div>'}</div></section>`);
  }
  // 2. a company (listed symbol or org name)
  const symHit = (ctx.data.symbols || []).find(([sym, name]) => sym.toLowerCase() === s.toLowerCase().replace(/^who.*about\s+/, "") || name.toLowerCase().startsWith(s.toLowerCase().replace(/^(who knows|who should i call about|call about)\s+/, "")));
  const orgHits = net.orgsInText(s.replace(/\b\w/g, (ch) => ch.toUpperCase()));   // people don't type proper nouns
  const orgId = orgHits.find((id) => !["kotak-ie"].includes(id)) || (symHit ? symHit[0] : null);
  if (orgId) {
    const ppl = net.whoToCall(orgId, { n: 5 });
    out.push(`<section class="section"><div class="section-head"><h2 class="h2">Who to call about ${esc(net.orgName(orgId))}</h2></div>
      <div class="list">${ppl.map((x) => personRow(x.person, ctx, x.text)).join("") || '<div class="empty">Nobody close to this company yet.</div>'}</div></section>`);
  }
  // 3. a theme
  const theme = net.themeFromText(s);
  if (theme) {
    const ex = net.expertise().find((x) => x.theme === theme);
    out.push(`<section class="section"><div class="section-head"><h2 class="h2">${esc(THEMES[theme])}</h2><span class="count">${ex ? ex.people.length : 0}</span></div>
      <div class="list">${ex ? ex.people.slice(0, 6).map((x) => personRow(x.person, ctx, x.why)).join("") : '<div class="empty">No one yet.</div>'}</div></section>`);
  }
  // 4. a contact by name
  const contacts = net.search(s).slice(0, 5);
  if (contacts.length && !pub) out.push(`<section class="section"><div class="section-head"><h2 class="h2">People</h2></div><div class="list">${contacts.map((p) => personRow(p, ctx)).join("")}</div></section>`);
  return out.join("") || `<div class="empty"><div class="h2">Nothing yet</div><p>Try a company (“Kaynes”), a theme (“specialty chemicals”), or a person in the news (“Anup Bagchi”).</p></div>`;
}

export function renderNetwork(ctx, q = "") {
  const net = ctx.net;
  const nudges = net.nudges(ctx.data.events.map((e) => ({ ...e, headline: headline(e) })), 4);
  const ex = net.expertise();
  const cold = net.people.map((p) => ({ p, t: net.tie(p) })).filter((x) => x.t.months >= 6).sort((a, b) => b.t.months - a.t.months);
  const pubPeople = [...new Map(ctx.data.events.flatMap((e) => (e.people || []).filter((p) => p.change === "appointed").map((p) => [p.name, { p, e }]))).values()];
  const suggestions = [
    pubPeople[0] ? `Path to ${pubPeople[0].p.name}` : null, "Who knows Kaynes?", "Specialty chemicals", "Rural lending", "Semiconductors", "Page Industries",
  ].filter(Boolean);
  return `<div class="view">
    <header class="top"><div class="eyebrow">Network · on this device only</div><div class="h1">Who can help you understand it</div>
      <div class="sub">${net.people.length} people · ${Object.keys(THEMES).length} themes · inferred from careers you already know about</div></header>
    <form class="ask" data-ask="network"><span>${ICON.search}</span><input name="q" value="${esc(q)}" placeholder="A company, a theme, or someone in the news" autocomplete="off"></form>
    <div class="suggest">${suggestions.map((s) => `<button class="chip" data-askq="${esc(s)}">${esc(s)}</button>`).join("")}</div>
    <div id="answer">${q ? answer(q, ctx) : ""}</div>
    ${!q && pubPeople.length ? `<section class="section"><div class="section-head"><h2 class="h2">New faces in your portfolio</h2></div>
      <div class="list">${pubPeople.slice(0, 4).map(({ p, e }) => {
        const { paths } = net.pathsTo(p, 1);
        return `<a class="row" href="#/e/${e.id}"><span class="avatar">${initials(p.name)}</span><span class="grow"><div class="title">${esc(p.name)}</div>
        <div class="meta">${esc(p.role)} · ${esc(shortCo(e.company))}</div>
        <div class="meta" style="color:var(--accent)">${paths[0] ? `via ${esc(paths[0].person.name)}` : "no path yet"}</div></span></a>`;
      }).join("")}</div></section>` : ""}
    ${!q && nudges.length ? `<section class="section"><div class="section-head"><h2 class="h2">Reasons to reconnect</h2></div>
      ${nudges.map((n) => `<a class="card soft tap" href="#/p/${n.person.id}" style="display:block"><div style="font-weight:700">${esc(n.person.name)} <span class="muted small">· ${Math.round(n.tie.months)} months</span></div><p class="body" style="margin:6px 0 0">${esc(n.text)}</p></a>`).join("")}</section>` : ""}
    ${!q ? `<section class="section"><div class="section-head"><h2 class="h2">Expertise map</h2><span class="tiny muted">years in sector + your tags</span></div>
      ${ex.map((t) => `<div class="card"><div class="card-top"><b>${esc(t.label)}</b><span class="count">${t.people.length}</span></div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${t.people.slice(0, 5).map((x) => `<a class="pill blue" href="#/p/${x.person.id}" title="${esc(x.why)}">${esc(x.person.name.replace(/^(Dr\.|Prof\.|Col\.)\s*(\(retd\.\)\s*)?/, ""))}</a>`).join("")}</div></div>`).join("")}</section>` : ""}
    ${!q && cold.length ? `<section class="section"><details><summary class="section-head"><h2 class="h2">Gone quiet <span class="count">${cold.length}</span></h2><span class="link">Show</span></summary>
      <div class="list">${cold.map((x) => personRow(x.p, ctx, `${Math.round(x.t.months)} months since you spoke · ${x.p.headline}`)).join("")}</div></details></section>` : ""}
    <p class="note" style="margin-top:22px">This network is synthetic demo data. In real use it is built from your own LinkedIn export, calendar and notes, stays on your device, and is never sent to a model. Links to people in filings are inferred from overlapping employers, years and roles — never asserted.</p>
  </div>`;
}

export function renderPerson(id, ctx) {
  const net = ctx.net;
  const p = net.byId[id];
  if (!p) return `<div class="view"><a class="back" href="#/network">${ICON.back} Network</a><div class="empty">Not found.</div></div>`;
  const t = net.tie(p);
  const cur = net.current(p);
  // what can they help with right now?
  const relevant = [];
  for (const e of ctx.data.events.filter((x) => x.tier !== "routine")) {
    const st = p.career.find((c) => c.org_id === e.symbol);
    if (st) relevant.push({ e, why: `${st.end ? "Worked" : "Works"} there (${st.role}, ${st.start}–${st.end ?? "now"})` });
    const named = net.orgsInText([e.title, e.summary_src, e.brief?.one_line, e.brief?.so_what].join(" "));
    const cp = p.career.find((c) => c.org_id !== e.symbol && named.includes(c.org_id));
    if (cp) relevant.push({ e, why: `${cp.end ? "Was" : "Is"} ${cp.role} at ${net.orgName(cp.org_id)} — the other party named in this filing` });
    for (const pp of e.people || []) {
      const l = net.link(p, pp);
      if (l && l.score >= 0.3) relevant.push({ e, why: l.text });
    }
  }
  const holdings = ctx.symbols.filter((s) => net.whoToCall(s, { n: 8 }).some((x) => x.person.id === p.id));
  const tl = [...p.career].sort((a, b) => (b.end ?? 9999) - (a.end ?? 9999)).map((c) => {
    const inBook = ctx.symbols.includes(c.org_id);
    return `<div class="tl ${inBook ? "hit" : ""}"><div class="when">${c.start}–${c.end ?? "now"}</div><div class="what">${esc(c.role)}</div>
      <div class="small"><a class="${inBook ? "link" : "muted"}" href="${inBook ? `#/r/${c.org_id}` : "javascript:void 0"}">${esc(net.orgName(c.org_id))}</a>${inBook ? ' <span class="pill blue">in your book</span>' : ""}</div></div>`;
  }).join("");
  const edu = (p.education || []).map((e) => `<span class="pill">${esc(net.orgName(e.org_id))} · ${esc(e.degree)} ${e.end}</span>`).join(" ");
  const sharedEdu = (p.education || []).filter((e) => net.me.education.some((m) => m.org_id === e.org_id));
  return `<div class="view">
    <a class="back" href="javascript:history.back()">${ICON.back} Back</a>
    <header class="top" style="text-align:left">
      <div class="co"><span class="avatar lg">${initials(p.name)}</span><span><div class="h1" style="margin:0">${esc(p.name)}</div><div class="small muted">${esc(p.headline)} · ${esc(p.city || "")}</div></span></div>
    </header>
    <div class="card soft">
      <dl class="kv"><dt>How you know them</dt><dd>${esc(p.relation.context)}</dd>
      <dt>Link</dt><dd>${esc(t.label)} ${net.bars(t.score)} · your ${esc(t.rel)}</dd>
      <dt>Last spoke</dt><dd>${new Date(p.last_contact).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} · ${Math.round(t.months)} months ago · ${p.touches_12m} touch${p.touches_12m === 1 ? "" : "es"} this year</dd>
      ${sharedEdu.length ? `<dt>In common</dt><dd>${sharedEdu.map((e) => esc(net.orgName(e.org_id))).join(", ")}</dd>` : ""}
      <dt>Source</dt><dd class="muted">${esc({ linkedin_export: "Your LinkedIn export", calendar: "Your calendar", manual: "Added by you" }[p.source] || p.source)}</dd></dl>
    </div>
    ${relevant.length ? `<section class="section"><div class="section-head"><h2 class="h2">Can help with, right now</h2></div>
      <div class="list">${relevant.slice(0, 4).map(({ e, why }) => `<a class="row" href="#/e/${e.id}" style="align-items:flex-start"><span class="logo">${esc(e.symbol.slice(0, 3))}</span><span class="grow"><div class="title" style="white-space:normal">${esc(headline(e))}</div><div class="meta" style="white-space:normal">${esc(why)}</div></span></a>`).join("")}</div></section>` : ""}
    ${holdings.length ? `<section class="section"><div class="section-head"><h2 class="h2">Useful on</h2></div><div style="display:flex;flex-wrap:wrap;gap:6px">${holdings.map((s) => `<a class="pill blue" href="#/r/${s}">${esc(shortCo(ctx.names[s] || s))}</a>`).join("")}</div></section>` : ""}
    <section class="section"><div class="section-head"><h2 class="h2">Career</h2></div><div class="timeline">${tl}</div>${edu ? `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">${edu}</div>` : ""}</section>
    ${cur?.org_id && ctx.data.orgs[cur.org_id]?.listed ? `<p class="caution" style="margin-top:16px">${esc(p.name.split(" ")[0])} works at a listed company. Keep conversations to public information (SEBI PIT Regulations).</p>` : ""}
  </div>`;
}
