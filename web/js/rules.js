// Personal relevance + triggered alerts. Everything here is the investor's own judgement
// (thresholds, categories, position sizes) and is evaluated on the device.

const KEY = "finn.prefs.v1";

export const CATEGORY_LABEL = {
  results: "Results", "M&A": "M&A", fund_raise: "Fund raise", management_change: "Management", litigation: "Legal & regulatory",
  insider_trading: "Insider trades", earnings_call: "Earnings calls", investor_meetings: "Investor meets", credit_rating: "Credit ratings",
  dividend: "Dividends", bonus_split: "Bonus / split", capex: "Capex", press_release: "Orders & press", postal_ballot: "Postal ballots",
  agm_egm: "AGM / EGM", pledging: "Pledging", unclassified: "Routine paperwork",
};

export const DEFAULT_CARE = ["results", "M&A", "management_change", "litigation", "fund_raise", "pledging", "credit_rating", "capex", "press_release"];

export const WINDOWS = [
  { id: "24h", label: "24h", hours: 24 }, { id: "3d", label: "3 days", hours: 72 },
  { id: "7d", label: "7 days", hours: 168 }, { id: "30d", label: "30 days", hours: 720 },
];

export function loadPrefs(defaults) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { /* private mode */ }
  return {
    window: "24h", volume_multiple: defaults?.volume_multiple ?? 2, price_move_pct: defaults?.price_move_pct ?? 4,
    relative_to_index: defaults?.relative_to_index ?? true, care: DEFAULT_CARE, dismissed: [], ...saved,
  };
}

export function savePrefs(p) {
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* ignore */ }
}

export function windowStart(prefs, now) {
  const w = WINDOWS.find((x) => x.id === prefs.window) || WINDOWS[0];
  return new Date(now.getTime() - w.hours * 3600e3);
}

/** Personal relevance on top of the pipeline's intrinsic score. Returns {score, tier, reasons}. */
export function personalise(e, { weights, prefs, net }) {
  let s = e.score;
  const reasons = [...(e.reasons || [])];
  const w = weights[e.symbol] || 0;
  if (w) {
    s += Math.min(8, w * 0.8);
    reasons.push(`${w}% of your book`);
  }
  if (!prefs.care.includes(e.category) && e.category !== "unclassified") {
    s -= 12;
  }
  if (net) {
    const close = net.people.filter((p) => p.career.some((c) => c.org_id === e.symbol));
    if (close.length && e.score >= 40) {
      s += 4;
      reasons.push(`You know ${close.length} ${close.length > 1 ? "people" : "person"} who worked here`);
    }
  }
  s = Math.max(0, Math.min(100, s));
  const tier = s >= 70 ? "material" : s >= 40 ? "notable" : "routine";
  return { score: s, tier, reasons };
}

/** EOD triggers: volume >= k x 20-day avg, |move| >= X% (optionally net of Nifty). */
export function eodAlerts(eod, symbols, prefs, since) {
  const idx = Object.fromEntries((eod["^NSEI"] || []).map((r) => [r[0], r[1]]));
  const out = [];
  for (const sym of symbols) {
    const rows = eod[sym] || [];
    for (let i = 21; i < rows.length; i++) {
      const [d, c, v] = rows[i];
      if (new Date(d + "T15:30:00+05:30") < since) continue;
      const pc = rows[i - 1][1];
      const ret = (c / pc - 1) * 100;
      const prevIdxDate = rows[i - 1][0];
      const iret = idx[d] && idx[prevIdxDate] ? (idx[d] / idx[prevIdxDate] - 1) * 100 : null;
      const move = prefs.relative_to_index && iret !== null ? ret - iret : ret;
      const avg = rows.slice(i - 20, i).reduce((a, r) => a + r[2], 0) / 20;
      const vm = avg ? v / avg : 0;
      const hitMove = Math.abs(move) >= prefs.price_move_pct;
      const hitVol = vm >= prefs.volume_multiple;
      if (!hitMove && !hitVol) continue;
      out.push({ symbol: sym, date: d, close: c, ret, iret, move, vm, hitMove, hitVol, series: rows.slice(Math.max(0, i - 40), i + 1).map((r) => r[1]) });
    }
  }
  out.sort((a, b) => (b.date.localeCompare(a.date)) || (Math.abs(b.move) - Math.abs(a.move)));
  return out;
}

/** Explain a move with a same-window filing, or say plainly that nothing explains it. */
export function explainMove(alert, events) {
  const d = new Date(alert.date + "T15:30:00+05:30");
  const cands = events.filter((e) => e.symbol === alert.symbol && e.tier !== "routine" && d - new Date(e.dt) <= 3 * 864e5 && d - new Date(e.dt) >= -864e5 / 2);
  cands.sort((a, b) => b.score - a.score);
  return cands[0] || null;
}
