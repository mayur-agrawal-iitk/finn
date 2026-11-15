// Formatting + tiny SVG charts. No dependencies.

const IN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const IN1 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function inr(v, unit = "cr") {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const neg = v < 0;
  const a = Math.abs(v);
  const s = a >= 100 ? IN.format(a) : IN1.format(a);
  return `${neg ? "−" : ""}₹${s}${unit ? " " + unit : ""}`;
}

export function num(v, dp = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp }).format(v);
}

export function pct(v, dp = 1, sign = true) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = Math.abs(v).toFixed(dp);
  return `${v < 0 ? "−" : sign && v > 0 ? "+" : ""}${s}%`;
}

export function signCls(v, invert = false) {
  if (v === null || v === undefined || Math.abs(v) < 0.05) return "";
  return (v > 0) !== invert ? "pos" : "neg";
}

export function ago(iso, now = new Date()) {
  const d = new Date(iso);
  const m = (now - d) / 60000;
  if (m < 60) return `${Math.max(1, Math.round(m))}m ago`;
  if (m < 60 * 24) return `${Math.round(m / 60)}h ago`;
  if (m < 60 * 24 * 7) return `${Math.round(m / 1440)}d ago`;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const dshort = (iso) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
export const monthsSince = (iso, now = new Date()) => (now - new Date(iso)) / (1000 * 60 * 60 * 24 * 30.44);
export const initials = (name) => name.replace(/^(Dr\.|Prof\.|Col\.|\(retd\.\))\s*/g, "").replace(/\(.*?\)/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
export const logoText = (sym) => (sym || "").replace(/[^A-Z]/g, "").slice(0, 3);
export const yrs = (a, b) => `${a ?? "?"}–${b ?? "now"}`;

export function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 1800);
}

// ---------------------------------------------------------------- charts

export function spark(values, { w = 84, h = 28, color } = {}) {
  const v = values.filter((x) => x !== null && x !== undefined);
  if (v.length < 2) return "";
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const pts = v.map((y, i) => `${((i / (v.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((y - lo) / span) * (h - 4)).toFixed(1)}`).join(" ");
  const c = color || (v[v.length - 1] >= v[0] ? "var(--pos)" : "var(--neg)");
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/></svg>`;
}

/** Bars (one or two series) with an optional line on a right axis. Values may be negative. */
export function bars({ labels, series, line = null, w = 400, h = 170, fmt = (x) => x, lineFmt = (x) => x }) {
  const padL = 6, padR = line ? 30 : 6, padT = 14, padB = 22;
  const all = series.flatMap((s) => s.values).filter((x) => x !== null && x !== undefined);
  if (!all.length) return "";
  const max = Math.max(0, ...all), min = Math.min(0, ...all), span = max - min || 1;
  const iw = w - padL - padR, ih = h - padT - padB;
  const y = (v) => padT + ((max - v) / span) * ih;
  const n = labels.length, gw = iw / n, bw = Math.min(22, (gw * 0.7) / series.length);
  let g = `<line x1="${padL}" x2="${w - padR}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>`;
  labels.forEach((lab, i) => {
    const cx = padL + gw * i + gw / 2;
    series.forEach((s, k) => {
      const v = s.values[i];
      if (v === null || v === undefined) return;
      const x = cx - (bw * series.length) / 2 + k * bw + 1;
      const y0 = y(Math.max(0, v)), hgt = Math.abs(y(v) - y(0));
      g += `<rect x="${x.toFixed(1)}" y="${y0.toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${Math.max(1, hgt).toFixed(1)}" rx="3" fill="${v < 0 ? "var(--neg)" : s.color}"><title>${esc(lab)} · ${esc(s.name || "")} ${esc(fmt(v))}</title></rect>`;
    });
    if (n <= 12 || i % Math.ceil(n / 8) === 0 || i === n - 1) g += `<text x="${cx}" y="${h - 6}" text-anchor="middle">${esc(lab)}</text>`;
  });
  if (line) {
    const lv = line.values.filter((x) => x !== null && x !== undefined);
    if (lv.length >= 2) {
      const lmax = Math.max(...lv), lmin = Math.min(...lv), ls = lmax - lmin || 1;
      const ly = (v) => padT + 8 + ((lmax - v) / ls) * (ih - 16);
      const pts = line.values.map((v, i) => (v === null || v === undefined ? null : `${(padL + gw * i + gw / 2).toFixed(1)},${ly(v).toFixed(1)}`)).filter(Boolean);
      g += `<polyline fill="none" stroke="${line.color}" stroke-width="2" stroke-linejoin="round" points="${pts.join(" ")}"/>`;
      line.values.forEach((v, i) => { if (v !== null && v !== undefined) g += `<circle cx="${(padL + gw * i + gw / 2).toFixed(1)}" cy="${ly(v).toFixed(1)}" r="2.5" fill="#fff" stroke="${line.color}" stroke-width="1.5"><title>${esc(labels[i])} · ${esc(line.name || "")} ${esc(lineFmt(v))}</title></circle>`; });
      g += `<text x="${w - 2}" y="${ly(lmax) + 3}" text-anchor="end">${esc(lineFmt(lmax))}</text><text x="${w - 2}" y="${ly(lmin) + 3}" text-anchor="end">${esc(lineFmt(lmin))}</text>`;
    }
  }
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img">${g}</svg>`;
}

export function stack(parts) {
  const tot = parts.reduce((a, p) => a + (p.v || 0), 0) || 1;
  return `<div class="meter">${parts.map((p) => `<span style="width:${((p.v || 0) / tot) * 100}%;background:${p.c}" title="${esc(p.k)} ${Math.round(((p.v || 0) / tot) * 100)}%"></span>`).join("")}</div>
  <div class="legend">${parts.filter((p) => p.v).map((p) => `<span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${p.c};margin-right:5px"></i>${esc(p.k)} ${Math.round((p.v / tot) * 100)}%</span>`).join("")}</div>`;
}

export const ICON = {
  brief: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h10M4 18h7"/><circle cx="19" cy="16.5" r="2.5"/></svg>`,
  research: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>`,
  network: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="7" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="17.5" r="2.5"/><path d="M8 8.5l2.8 6.8M16 8.5l-2.8 6.8M8.5 7h7"/></svg>`,
  watch: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-7 4 14 3-7h4"/></svg>`,
  search: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>`,
  back: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>`,
  ext: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M9 7h8v8"/></svg>`,
  phone: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/></svg>`,
  x: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
};
