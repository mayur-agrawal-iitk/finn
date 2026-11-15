// The Network engine. Runs entirely on the device: the investor's contacts never leave it.
// It joins PUBLIC data (people named in filings, companies, events) with the PRIVATE graph
// on organisation ids, and explains every inference in words.

import { monthsSince } from "./lib.js";

export const THEMES = {
  specialty_chem: "Specialty chemicals",
  rural_lending: "Rural & small-ticket lending",
  semis_electronics: "Electronics & semiconductors",
  defence: "Defence & aerospace",
  banking: "Banking & credit",
  insurance: "Insurance",
  retail_consumer: "Retail & consumer",
  fmcg: "FMCG",
  healthcare: "Healthcare delivery",
  it_services: "IT services",
  auto_engineering: "Auto & engineering",
  capital_markets: "Capital markets",
  legal_regulatory: "Legal & regulatory",
  energy_conglomerate: "Energy & conglomerates",
};

const REL_BASE = { family_friend: 0.85, friend: 0.85, classmate: 0.8, ex_colleague: 0.8, alumni: 0.55, industry: 0.5, introduced: 0.45, friend_of_friend: 0.3 };
const REL_LABEL = { family_friend: "family friend", friend: "friend", classmate: "classmate", ex_colleague: "ex-colleague", alumni: "alumni", industry: "industry contact", introduced: "introduced", friend_of_friend: "friend of a friend" };
const SIZE_BASE = { 1: 0.75, 2: 0.6, 3: 0.45, 4: 0.35 };
const FN_WORDS = {
  rural_banking: ["rural", "inclusive", "agri"], retail_banking: ["retail"], wholesale_banking: ["wholesale", "corporate"],
  research: ["research"], sales: ["sales", "key account", "trade", "merchandis"], merchandising: ["merchandis", "category", "fmcg"],
  finance: ["finance", "cfo", "financial", "controller"], distribution: ["distribution", "bancassurance"], operations: ["operations"],
  strategy: ["strategy"], engineering: ["engineer", "r&d", "design"],
};

// "Dr. Kavya Reddy" -> "Kavya"; "P B Rangarao" -> "Rangarao" (initials aren't names); "Mr. X" -> "X".
const first = (name) => {
  const toks = name.replace(/^(Dr\.|Prof\.|Col\.|Mr\.|Mrs\.|Ms\.|Shri|Smt\.?)\s*(\(retd\.\)\s*)?/i, "").split(/\s+/).filter(Boolean);
  const real = toks.find((t) => t.replace(/\./g, "").length > 1);
  return toks.length && toks[0].replace(/\./g, "").length <= 1 ? toks[toks.length - 1] : (real || toks[0] || name);
};

export class Network {
  constructor(net, orgs, now = new Date()) {
    this.net = net;
    this.orgs = orgs;
    this.now = now;
    this.Y = now.getFullYear();
    this.people = net.people;
    this.byId = Object.fromEntries(net.people.map((p) => [p.id, p]));
    this.me = net.investor;
    this.aliasIndex = this._aliases();
  }

  /** The same public person can appear in several filings (a notice, then the approval). Use the richest record. */
  indexPublicPeople(events) {
    this.publicPeople = {};
    for (const e of events) {
      for (const p of e.people || []) {
        const k = p.name.toLowerCase().replace(/^(mr|mrs|ms|dr|shri)\.?\s+/, "").trim();
        const cur = this.publicPeople[k];
        const richness = (x) => (x.career?.length || 0) * 2 + (x.education?.length || 0) + (x.bio ? 1 : 0);
        if (!cur || richness(p) > richness(cur)) this.publicPeople[k] = p;
      }
    }
  }

  richest(p) {
    const k = p.name.toLowerCase().replace(/^(mr|mrs|ms|dr|shri)\.?\s+/, "").trim();
    const r = this.publicPeople?.[k];
    return r ? { ...p, career: r.career, education: r.education, bio: p.bio || r.bio, age: p.age || r.age } : p;
  }

  org(id) { return this.orgs[id] || { name: id }; }
  orgName(id) { return this.org(id).name || id; }

  _aliases() {
    const out = [];
    for (const [id, o] of Object.entries(this.orgs)) {
      for (const a of [o.name, ...(o.aliases || [])]) {
        if (a && a.length >= 4) out.push([a.toLowerCase(), id, a]);
      }
    }
    return out.sort((a, b) => b[0].length - a[0].length);
  }

  /** Organisations named in free text (e.g. a deal counterparty in a filing summary). */
  orgsInText(text) {
    const raw = ` ${String(text || "")} `;
    const t = raw.toLowerCase();
    const hits = new Set();
    const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    for (const [a, id, orig] of this.aliasIndex) {
      // One-word aliases must appear as the proper noun ("Ambit", not "within the ambit of").
      const single = !/\s/.test(a);
      const re = single ? new RegExp(`[^A-Za-z]${escRe(orig)}[^A-Za-z]`) : new RegExp(`[^a-z]${escRe(a)}[^a-z]`);
      if (re.test(single ? raw : t)) hits.add(id);
    }
    return [...hits];
  }

  // ---------------------------------------------------------- first-degree tie strength
  tie(p) {
    const base = REL_BASE[p.relation?.type] ?? 0.4;
    const m = p.last_contact ? monthsSince(p.last_contact, this.now) : 36;
    const recency = Math.max(0.35, Math.exp(-m / 24));
    const freq = 0.12 * Math.min(p.touches_12m || 0, 6) / 6;
    const score = Math.min(1, base * recency + freq);
    const label = score >= 0.62 ? "strong" : score >= 0.42 ? "medium" : "weak";
    return { score, label, months: m, rel: REL_LABEL[p.relation?.type] || "contact" };
  }

  bars(score) {
    const n = score >= 0.62 ? 3 : score >= 0.42 ? 2 : 1;
    return `<span class="strength" title="${["weak", "medium", "strong"][n - 1]} link">${[1, 2, 3].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
  }

  current(p) { return p.career.find((c) => c.end === null) || p.career[0]; }

  // ---------------------------------------------------------- inferred links to a public person
  /** How might contact `p` know the person in a filing? Returns the strongest explained link. */
  link(p, target) {
    let best = null;
    const tName = first(target.name);
    for (const t of target.career || []) {
      if (!t.org_id) continue;
      for (const c of p.career) {
        if (c.org_id !== t.org_id) continue;
        const o = this.org(c.org_id);
        const base = SIZE_BASE[o.size || 3];
        const cs = c.start, ce = c.end ?? this.Y;
        let score, text, confidence = "high";
        if (t.start_year == null && t.end_year == null) {
          score = base * 0.55;
          confidence = "low";
          text = `${first(p.name)} was ${c.role} at ${o.name} (${cs}–${c.end ?? "now"}); the filing doesn't give ${tName}'s years there, so the overlap is unconfirmed.`;
        } else {
          const ts = t.start_year ?? 1900, te = t.end_year ?? this.Y;
          const ov = Math.min(ce, te) - Math.max(cs, ts);
          if (ov < 0) continue;
          const roleText = (t.role || "").toLowerCase();
          const fnMatch = (FN_WORDS[c.function] || []).some((w) => roleText.includes(w));
          const leader = (c.seniority || 0) >= 4 && /ceo|managing|director|head|president|chief/.test(roleText);
          score = Math.min(0.95, base + (fnMatch ? 0.2 : 0) + (leader ? 0.1 : 0) + Math.min(0.12, ov * 0.03));
          // A junior person in a big organisation rarely works directly with its top leadership.
          const gap = /ceo|managing|executive director|president|chief/.test(roleText) && (c.seniority || 0) <= 2;
          if (gap) score *= 0.6;
          const span = `${Math.max(cs, ts)}–${Math.min(ce, te) === this.Y ? "now" : Math.min(ce, te)}`;
          text = `${first(p.name)} was ${c.role} at ${o.name} (${cs}–${c.end ?? "now"}) while ${tName} was ${t.role ? t.role.replace(/^(the )/i, "") : "there"} — about ${Math.max(1, ov)} yr${ov > 1 ? "s" : ""} together (${span})${fnMatch ? ", in the same line of business" : ""}${gap ? ", though several levels apart" : ""}.`;
        }
        if (!best || score > best.score) best = { score, text, org_id: c.org_id, kind: "worked", confidence };
      }
    }
    for (const t of target.education || []) {
      if (!t.org_id) continue;
      for (const e of p.education || []) {
        if (e.org_id !== t.org_id) continue;
        const o = this.org(e.org_id);
        let score, text;
        if (t.year && Math.abs((e.end || 0) - t.year) <= 1) {
          score = 0.55; text = `${first(p.name)} and ${tName} overlapped at ${o.name} (${e.end} / ${t.year}).`;
        } else {
          score = 0.15; text = `${first(p.name)} and ${tName} are both ${o.name} alumni${t.year ? ` (${e.end} vs ${t.year})` : ""} — a weak tie, but an opener.`;
        }
        if (!best || score > best.score) best = { score, text, org_id: e.org_id, kind: "studied", confidence: t.year ? "high" : "low" };
      }
    }
    return best;
  }

  /** Ranked second-degree paths from you to a public person (e.g. an incoming CEO). */
  pathsTo(target, n = 3) {
    target = this.richest(target);
    const out = [];
    for (const p of this.people) {
      const l = this.link(p, target);
      if (!l) continue;
      const t = this.tie(p);
      out.push({ person: p, tie: t, link: l, score: t.score * l.score });
    }
    out.sort((a, b) => b.score - a.score);
    const mine = this.link({ ...this.me, name: "You" }, target);
    return { paths: out.slice(0, n), total: out.length, you: mine };
  }

  // ---------------------------------------------------------- who should I call about X?
  whoToCall(orgId, { counterparties = [], topics = [], n = 3 } = {}) {
    const meta = this.org(orgId);
    // Topics come from the public filing's brief ("FEMA compliance", "defence procurement"); they are matched
    // to contacts' themes here, on the device, so contacts never have to be sent anywhere.
    const topicThemes = topics.map((t) => [t, this.themeFromText(t)]).filter(([, th]) => th && th !== meta.theme);
    const res = [];
    for (const p of this.people) {
      let best = null;
      let alum = null;
      for (const c of p.career) {
        const cur = c.end === null;
        const fresh = cur ? 1 : Math.max(0.35, Math.exp(-(this.Y - c.end) / 8));
        const o = this.org(c.org_id);
        let rel = 0, kind = "", text = "";
        if (counterparties.includes(c.org_id) && c.org_id !== orgId) {
          rel = 1.0 * fresh; kind = "counterparty";
          text = `${cur ? "" : "Was "}${c.role} at ${o.name}${cur ? "" : ` (${c.start}–${c.end})`} — the other side of this deal.`;
        } else if (c.org_id === orgId) {
          rel = cur ? 0.8 : 1.0 * fresh; kind = cur ? "insider" : "alumnus";
          text = cur ? `Works there now — ${c.role}.` : `${c.role}, ${c.start}–${c.end}. Knows the people and the plumbing.`;
        } else if (o.industry && meta.industry && o.industry === meta.industry) {
          rel = 0.62 * fresh; kind = "competitor";
          text = `${cur ? "" : "Was "}${c.role} at ${o.name}${cur ? "" : ` (${c.start}–${c.end})`} — a direct peer in ${meta.industry.toLowerCase()}.`;
        } else if (o.theme && meta.theme && o.theme === meta.theme) {
          rel = 0.42 * fresh; kind = "sector";
          text = `${c.role} at ${o.name} — same sector (${THEMES[meta.theme] || meta.theme}).`;
        }
        if (kind === "alumnus") alum = { rel, text, c };
        if (rel && (!best || rel > best.rel)) best = { rel, kind, text, insider: kind === "insider" && o.listed };
      }
      if (best && alum && best.kind !== "alumnus") {
        // Two angles on the same company (worked there AND now at a peer) beat either alone.
        best = { ...best, rel: Math.min(1.1, best.rel + 0.15), text: `${best.text} Before that: ${alum.c.role} at ${this.orgName(alum.c.org_id)}, ${alum.c.start}–${alum.c.end}.` };
      }
      const topicHit = topicThemes.find(([, th]) => (p.tags || []).includes(th));
      if (topicHit && (!best || best.rel < 0.6)) {
        const topic = /^[A-Z]{2,}/.test(topicHit[0]) ? topicHit[0] : topicHit[0].charAt(0).toLowerCase() + topicHit[0].slice(1);
        best = { rel: 0.6, kind: "expertise", text: `${best ? best.text + " " : ""}Your go-to on ${topic}.` };
      }
      if (!best && meta.theme && (p.tags || []).includes(meta.theme)) {
        best = { rel: 0.35, kind: "expertise", text: `Your go-to on ${(THEMES[meta.theme] || meta.theme).toLowerCase()}.` };
      }
      if (!best) continue;
      const t = this.tie(p);
      res.push({ person: p, tie: t, ...best, score: best.rel * (0.45 + 0.55 * t.score) - (best.insider ? 0.08 : 0) });
    }
    res.sort((a, b) => b.score - a.score);
    return res.slice(0, n);
  }

  // ---------------------------------------------------------- expertise map
  expertise() {
    const out = [];
    for (const [theme, label] of Object.entries(THEMES)) {
      const ppl = [];
      for (const p of this.people) {
        let years = 0;
        const where = new Set();
        for (const c of p.career) {
          if (this.org(c.org_id).theme === theme) {
            years += (c.end ?? this.Y) - c.start;
            where.add(this.org(c.org_id).name);
          }
        }
        const tagged = (p.tags || []).includes(theme);
        const score = Math.min(12, years) / 12 * 0.75 + (tagged ? 0.25 : 0);
        if (score >= 0.25) ppl.push({ person: p, score, why: years ? `${years} yrs · ${[...where].slice(0, 2).join(", ")}` : "tagged by you" });
      }
      ppl.sort((a, b) => b.score - a.score);
      if (ppl.length) out.push({ theme, label, people: ppl });
    }
    out.sort((a, b) => b.people.length - a.people.length);
    return out;
  }

  // ---------------------------------------------------------- keep the network warm
  nudges(events, n = 3) {
    const out = [];
    const recent = events.filter((e) => e.tier !== "routine" && (this.now - new Date(e.dt)) / 864e5 <= 21);
    for (const p of this.people) {
      const t = this.tie(p);
      if (t.months < 4) continue;
      let best = null;
      for (const e of recent) {
        const st = p.career.find((c) => c.org_id === e.symbol);
        let reason = null;
        if (st) {
          const when = new Date(e.dt).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
          reason = `${e.company.replace(/ Ltd$/, "")} — where ${first(p.name)} ${st.end ? `worked until ${st.end}` : "works"} as ${st.role} — filed on ${when}: ${e.headline || e.title}.`;
        } else if (e.people?.length) {
          for (const person of e.people) {
            const l = this.link(p, this.richest(person));
            if (l && l.score >= 0.4) { reason = `${person.name}, ${e.company.replace(/ Ltd$/, "")}'s new ${person.role}, overlapped with ${first(p.name)} at ${this.orgName(l.org_id)}.`; break; }
          }
        }
        if (!reason) continue;
        const s = t.score * (e.score / 100) * Math.min(1.4, t.months / 6);
        if (!best || s > best.s) best = { s, e, reason };
      }
      if (best) out.push({ person: p, tie: t, event: best.e, text: best.reason, score: best.s });
    }
    out.sort((a, b) => b.score - a.score);
    return out.slice(0, n);
  }

  // ---------------------------------------------------------- lookups
  search(q) {
    const s = q.toLowerCase();
    return this.people.filter((p) => p.name.toLowerCase().includes(s) || p.headline.toLowerCase().includes(s)
      || p.career.some((c) => this.orgName(c.org_id).toLowerCase().includes(s)));
  }

  themeFromText(q) {
    const s = q.toLowerCase();
    // Order matters: the more specific theme wins ("defence electronics" is defence; "FEMA rules" is legal).
    const syn = [
      ["defence", ["defence", "defense", "aero", "military", "naval"]], ["legal_regulatory", ["legal", "regulat", "fema", "sebi", "law", "compliance", "litigation"]],
      ["specialty_chem", ["chem", "fluoro", "specialty", "refrigerant"]], ["rural_lending", ["rural", "microfinance", "mfi", "affordable housing"]],
      ["semis_electronics", ["semicon", "electronic", "ems", "chip", "osat", "pcb"]], ["insurance", ["insur"]], ["banking", ["bank", "credit", "lending"]],
      ["fmcg", ["fmcg", "staples", "packaged food"]], ["retail_consumer", ["retail", "consumer", "merchandis"]], ["healthcare", ["health", "hospital", "pharma"]],
      ["it_services", ["it services", "software", "tech services"]], ["auto_engineering", ["auto", "engineering", "ev"]],
      ["capital_markets", ["capital market", "broking", "amc", "qualified institutional", "placement"]], ["energy_conglomerate", ["energy", "oil", "conglomerate"]],
    ];
    const short = new Set(["ems", "mfi", "amc", "law", "ev", "pcb"]);
    for (const [k, words] of syn) {
      if (words.some((w) => new RegExp(`\\b${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${short.has(w) ? "\\b" : ""}`).test(s))) return k;
    }
    return null;
  }
}
