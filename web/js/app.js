// FINN — app shell: data loading, routing, interaction. Static, no framework, no build step.
import { ICON, toast } from "./lib.js";
import { Network } from "./network.js";
import { loadPrefs, personalise, savePrefs, windowStart } from "./rules.js";
import { renderBrief } from "./views/brief.js";
import { renderEvent } from "./views/event.js";
import { answer, renderNetwork, renderPerson } from "./views/network.js";
import { loadDossier, renderCompany, renderMissing, renderResearchHome } from "./views/research.js";
import { renderWatch } from "./views/watch.js";

const $main = document.getElementById("app");
const $tabs = document.getElementById("tabs");
const ctx = { api: (window.FINN_API || "").replace(/\/$/, ""), dossier: null };

async function getJSON(path, fallback = null) {
  try {
    const r = await fetch(path, { cache: "no-cache" });
    return r.ok ? await r.json() : fallback;
  } catch {
    return fallback;
  }
}

async function boot() {
  getJSON(`${ctx.api ? ctx.api + "/" : ""}api/health`).then((h) => { ctx.live = !!h?.ok; });
  const [meta, portfolio, eod, events, network, orgs, index] = await Promise.all([
    getJSON("data/meta.json"), getJSON("data/portfolio.json"), getJSON("data/eod.json", {}), getJSON("data/events.json", []),
    getJSON("data/network.json"), getJSON("data/orgs.json", {}), getJSON("data/research/index.json", []),
  ]);
  if (!meta || !portfolio) {
    $main.innerHTML = `<div class="empty" style="padding-top:30vh"><div class="h2">No data yet</div><p>Run <code>python -m finn build</code> to populate <code>web/data/</code>.</p></div>`;
    return;
  }
  ctx.data = { meta, portfolio, eod, events, network, orgs, index, symbols: [] };
  // Windows are anchored to the data snapshot, so a stale snapshot never looks empty — and says how old it is.
  ctx.now = new Date(meta.generated_at);
  ctx.symbols = portfolio.holdings.map((h) => h.symbol);
  ctx.names = Object.fromEntries([...portfolio.holdings.map((h) => [h.symbol, h.name]), ...index.map((x) => [x.symbol, x.name])]);
  ctx.weights = Object.fromEntries(portfolio.holdings.map((h) => [h.symbol, h.weight]));
  ctx.net = network ? new Network(network, orgs, ctx.now) : null;
  ctx.net?.indexPublicPeople(events);
  ctx.prefs = loadPrefs(portfolio.rules);
  rescore();
  route();
  getJSON("data/symbols.json", []).then((s) => { ctx.data.symbols = s; if (location.hash.startsWith("#/research")) route(); });
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
}

function rescore() {
  ctx.scored = {};
  for (const e of ctx.data.events) ctx.scored[e.id] = personalise(e, { weights: ctx.weights, prefs: ctx.prefs, net: ctx.net });
  const since = windowStart(ctx.prefs, ctx.now);
  const n = ctx.data.events.filter((e) => new Date(e.dt) >= since && ctx.scored[e.id].tier === "material" && !ctx.prefs.dismissed.includes(e.id)).length;
  const badge = $tabs.querySelector('[data-route="brief"] .badge');
  if (badge) { badge.textContent = n; badge.style.display = n ? "" : "none"; }
}

function setPrefs(patch) {
  Object.assign(ctx.prefs, patch);
  savePrefs(ctx.prefs);
  rescore();
  route(false);
}

function parse() {
  const h = location.hash.replace(/^#\/?/, "") || "brief";
  const [path, qs] = h.split("?");
  const parts = path.split("/");
  return { parts, q: new URLSearchParams(qs || "") };
}

async function route(scrollTop = true) {
  const { parts, q } = parse();
  const top = parts[0];
  const tab = { brief: "brief", e: "brief", research: "research", r: "research", network: "network", p: "network", watch: "watch" }[top] || "brief";
  $tabs.querySelectorAll("a").forEach((a) => a.classList.toggle("on", a.dataset.route === tab));
  let html = "";
  if (top === "e") html = renderEvent(parts[1], ctx);
  else if (top === "research") html = renderResearchHome(ctx);
  else if (top === "r") {
    const sym = decodeURIComponent(parts[1] || "").toUpperCase();
    if (!ctx.dossier || ctx.dossier.symbol !== sym) {
      $main.innerHTML = `<div class="loading">Reading ${sym}'s filings…</div>`;
      ctx.dossier = await loadDossier(sym, ctx);
    }
    html = ctx.dossier ? renderCompany(ctx.dossier, ctx, q.get("tab") || "overview") : renderMissing(sym, ctx);
  } else if (top === "network") html = ctx.net ? renderNetwork(ctx, q.get("q") || "") : `<div class="empty">No network loaded.</div>`;
  else if (top === "p") html = renderPerson(parts[1], ctx);
  else if (top === "watch") html = renderWatch(ctx);
  else html = renderBrief(ctx);
  $main.innerHTML = html;
  if (scrollTop) window.scrollTo({ top: 0 });
}

// ------------------------------------------------------------------ interactions
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-window],[data-dismiss],[data-tab],[data-askq],[data-step],[data-care],[data-reset]");
  if (!t) return;
  if (t.dataset.window) return setPrefs({ window: t.dataset.window });
  if (t.dataset.dismiss) {
    ev.preventDefault();
    setPrefs({ dismissed: [...ctx.prefs.dismissed, t.dataset.dismiss] });
    return toast("Marked as done");
  }
  if (t.dataset.tab) {
    ev.preventDefault();
    const { parts } = parse();
    history.replaceState(null, "", `#/r/${parts[1]}?tab=${t.dataset.tab}`);
    route(false);
    document.querySelector(".seg")?.scrollIntoView({ block: "start" });
    return;
  }
  if (t.dataset.askq) { location.hash = `#/network?q=${encodeURIComponent(t.dataset.askq)}`; return; }
  if (t.dataset.step) {
    const k = t.dataset.step, d = +t.dataset.d;
    const v = Math.min(+t.dataset.max, Math.max(+t.dataset.min, Math.round((ctx.prefs[k] + d) * 10) / 10));
    return setPrefs({ [k]: v });
  }
  if (t.dataset.care) {
    const c = t.dataset.care;
    const care = ctx.prefs.care.includes(c) ? ctx.prefs.care.filter((x) => x !== c) : [...ctx.prefs.care, c];
    return setPrefs({ care });
  }
  if (t.dataset.reset !== undefined) {
    try { localStorage.removeItem("finn.prefs.v1"); } catch { /* ignore */ }
    ctx.prefs = loadPrefs(ctx.data.portfolio.rules);
    rescore(); route(false);
    return toast("Reset");
  }
});

document.addEventListener("change", (ev) => {
  const t = ev.target.closest("[data-pref]");
  if (t) setPrefs({ [t.dataset.pref]: t.checked });
});

document.addEventListener("submit", (ev) => {
  const f = ev.target.closest("form[data-ask]");
  if (!f) return;
  ev.preventDefault();
  const q = new FormData(f).get("q").toString().trim();
  if (!q) return;
  if (f.dataset.ask === "research") {
    const syms = ctx.data.symbols || [];
    const up = q.toUpperCase();
    const hit = syms.find(([s]) => s === up) || syms.find(([, n]) => n.toLowerCase().startsWith(q.toLowerCase()))
      || syms.find(([, n]) => n.toLowerCase().includes(q.toLowerCase())) || (ctx.data.index || []).map((x) => [x.symbol, x.name]).find(([, n]) => n.toLowerCase().includes(q.toLowerCase()));
    location.hash = `#/r/${hit ? hit[0] : up.replace(/\s+/g, "")}`;
  } else {
    location.hash = `#/network?q=${encodeURIComponent(q)}`;
    const a = document.getElementById("answer");
    if (a) a.innerHTML = answer(q, ctx);
  }
});

window.addEventListener("hashchange", () => route());

$tabs.innerHTML = [
  ["brief", "Brief", ICON.brief], ["research", "Research", ICON.research], ["network", "Network", ICON.network], ["watch", "Watch", ICON.watch],
].map(([r, l, i]) => `<a href="#/${r}" data-route="${r}">${i}<span>${l}</span>${r === "brief" ? '<span class="badge" style="display:none"></span>' : ""}</a>`).join("");

boot();
