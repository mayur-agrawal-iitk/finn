# FINN — Financial Investment Agent

**What changed in my portfolio, what did the company actually deliver, and who do I know who can explain it.**

FINN is a mobile-first investor workflow built for ENAM's Founding AI Engineer challenge by Mayur Agrawal
(IIT Kanpur, 220641). It runs on live NSE/BSE data for a 17-stock demo portfolio and any NSE symbol on demand.

- **Try it on your phone:** <https://mayur-agrawal-iitk.github.io/finn/> (static, refreshed by a cron) — add it to your home screen.
- **Run the live engine** (research on *any* NSE symbol): `pip install -r requirements.txt && python -m finn serve` → <http://127.0.0.1:8000>
- Architecture, privacy, models and cloud: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Covering note: [docs/COVER_NOTE.md](docs/COVER_NOTE.md)

<p>
  <img src="docs/screens/brief.png" width="260" alt="Brief: six things need you this week, Page Industries' results with the person best placed to explain">
  <img src="docs/screens/research.png" width="260" alt="Research: Kaynes management credibility 32/100 with the promise ledger">
  <img src="docs/screens/network.png" width="260" alt="Network: ranked paths to HDFC Bank's new CEO, each explained">
</p>

---

## A 60-second tour

1. **Brief** opens on the last 24 hours (data as of Sunday 15 Nov): *2 things need you*, both Kaynes.
   Tap **7 days**: *6 things need you · 33 filings across 15 holdings · 18 routine tucked away · 10 unusual
   moves*. Page Industries' Q2 card shows Revenue / EBITDA / PBT / PAT YoY and QoQ, and the stock's −13.1% vs
   Nifty the next session.
2. Every card ends in a person. Page's card names Ritika Shah — now CFO at a direct peer, earlier Page's
   financial controller. Page's FEMA clarification adds the lawyer you lean on for foreign-exchange rules.
   Tap **30 days** → HDFC Bank's new MD & CEO: **Anup Bagchi's career from the filing itself** and seven paths
   to him, led by an IIT-K classmate who ran ICICI Bank's rural banking (South) while Bagchi was the ED there.
3. **Unusual moves** are your rules (± X%, Y× volume, net of Nifty — set them in *Watch*) and each move is
   either explained by a nearby filing or flagged: *"No filing explains this move — worth a call."*
4. **Research → Kaynes**: the numbers are computed (5-year CFO/PAT −0.63x — profits not turning into cash;
   debtor days 74 → 154). **Promises** lists what management said on each call, verbatim with page links,
   scored against what was reported ("FY26 revenue at least ₹4,000 cr" → reported ₹3,626 cr: **missed**).
   Credibility **32/100**: *"cut its FY26 revenue guide from ₹4,500 cr to ₹4,000 cr and still delivered only
   ₹3,626 cr, and its FY26 OCF-positive promise was re-issued for FY27…"*
5. **Network → "specialty chemicals"** gives your go-to people by years in the sector. **Reconnect** finds
   people who have gone quiet and hands you a reason to call — *"Anup Bagchi, HDFC Bank's new MD & CEO,
   overlapped with Arjun at ICICI Bank"* (your classmate; last spoke 8 months ago).

## The point of view

- **A brief, not a feed.** The home screen answers "what do I need to know since I last looked" and
  stops. Ranking is explicit (what could move the stock × your position × your categories) and every card
  says *why it's here*.
- **Every item ends in a person or a source.** A filing is only useful if you can understand it; the
  fastest route is usually someone you know. The Network appears *inside* cards, at the moment it
  matters — not as a separate CRM.
- **Show the work.** Numbers link to filings; promises link to the transcript page; inferred
  relationships say what they're inferred from and how confident they are. Nothing is asserted that
  the data doesn't support.
- **Analyse management, don't summarise them.** The research view's centre of gravity is *promised vs
  delivered* — deterministic where the promise is numeric, model-judged only where it isn't.
- **Private by construction.** Your network and your settings never leave the device; models only read
  public documents.

## What's built

| Layer | Working workflows |
|---|---|
| **Push** | Windowed digest (24h / 3d / 7d / 30d) across the portfolio, ranked into *Needs you · Worth a glance · Routine*; results cards with Revenue / EBITDA / PBT / PAT QoQ & YoY (financing profit for lenders, with NPAs); management-change cards with the appointee's profile from the filing and network paths to them; material-event cards (M&A, legal, orders sized against revenue) with the best person to call and questions to ask; EOD triggers with configurable thresholds, index-relative moves and filing attribution. |
| **Pull** | A dossier for any NSE symbol: business, what's changing (multi-year trajectory in plain sentences), flags, numbers (12 quarters, 10 years), balance sheet (D/E, funding mix, working-capital cycle; asset quality for lenders), cash quality (CFO vs PAT, FCF), **promise ledger** with guidance drift and tone by call, management credibility, narrative vs numbers, bull/bear, questions to ask. Primary sources only. |
| **Network** | Tie strength (relationship × recency × frequency); inferred links to people in filings (overlapping employer, years, function, seniority, org size); who-to-call for any company (counterparty → alumni → competitor → sector → tagged expertise), insider-information caution; second-degree paths; expertise map; reconnect nudges; free-text ask ("Anup Bagchi", "Who knows Kaynes?", "rural lending"). |

**Portfolio (17):** HDFC Bank, Reliance, TCS, ITC, Bajaj Finance, HAL, BEL, DMart, Apollo Hospitals,
Kaynes, Navin Fluorine, Deepak Nitrite, Page Industries, Tube Investments, Amber, CreditAccess Grameen,
Aavas. **Research set (4, outside the portfolio):** SRF, Dixon, Cholamandalam Finance, Persistent.
Chosen to span banks/NBFCs (which need different metrics), defence PSUs, specialty chemicals, EMS,
consumer, healthcare — and the three themes the brief names (specialty chemicals, rural lending, semis).

## How it works (short version)

`python -m finn build` — fetch → classify (rules, 97.5% of filings) → enrich → research → write
`web/data/*.json`. The app is a static PWA that reads that folder. GitHub Actions runs the push side every
30 minutes on trading days and the full build every evening; Pages serves it. Model steps are
content-addressed and cached, so the daily refresh only pays for documents it has never seen. Details,
diagram and the privacy model: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Model step | Model | Volume |
|---|---|---|
| Guidance extraction from retrieved transcript passages (20% of the text) | Claude Haiku 5.5 | 4 calls/company |
| People in filings, one-line event briefs, results PDFs when tables lag, vague-title classification | Claude Haiku 5.5 | per material filing |
| Credibility, narrative vs numbers, bull/bear | Claude Opus 5.5 | 1 call/company/quarter |
| Everything else (classification, numbers, promise checks, drift, network) | code | — |

**What this demo cost to compute**, at API list prices: ≈ **$2.69** for 118 model outputs — 98 Haiku
extractions ($0.08 in total) and 20 Opus judgements (~13¢ each). 477 guidance quotes verified, 0 dropped.
A daily refresh costs ≈ $0 unless a company files something new.

## Honest notes

- **The network is synthetic.** 36 fictional contacts with realistic careers at real organisations, built
  to overlap with this portfolio. Overlaps with real executives are *inferred* from the public filing
  (employer + years), never asserted. In real use the network comes from the investor's own LinkedIn data
  export, calendar and notes, and stays on the device.
- **Model outputs in this build** were produced without an API key: the pipeline emitted each model
  step as a self-contained job (prompt + JSON schema), which was run offline on Claude Haiku 5.5 / Opus 5.5
  with the same prompts, then schema-validated and imported (`python -m finn llm-pending | llm-export |
  llm-check | llm-import`). Every cached record carries that provenance. With `ANTHROPIC_API_KEY` set,
  the same prompts run through the API.
- **Data limits.** screener.in exposes the five most recent filings per company, so the 45-day history
  is partial until the NSE RSS log has been running for a while (it starts at this build). One filing
  older than the poller was backfilled from NSE's archive (`data/backfill.json`). Some company IR sites
  block automated downloads; FINN falls back to the exchange copy of the transcript where it exists and
  says so where it doesn't. ITC does not publish concall transcripts, so it has no promise ledger.
- **Static vs live.** The Pages build carries 21 pre-built dossiers; any other symbol needs the live
  engine (`python -m finn serve`, or the one-click `render.yaml`).
- **Known analytical limits** (noted in the affected promises' evidence): lender KPIs (AUM, NIM, credit cost) aren't in the standardised tables, so
  most lender guidance is judged from later calls rather than computed; some companies' latest transcript
  lags their latest reported quarter; the extractor occasionally records the same promise twice or reads a
  segment target as company-level; *drift* only catches like-for-like numeric revisions, the synthesis
  catches the rest (e.g. Reliance's ARPU ambition easing from 5–6% to 4–5%). Fixes are on the roadmap:
  lender KPIs from investor presentations, and an eval set built from the verified-quote ledger.

## Run it

```bash
pip install -r requirements.txt
python -m finn build            # ~6 min cold, ~1 min warm; writes web/data/
python -m finn serve            # app + live research API on :8000
python -m finn research POLYCAB # one dossier for any NSE symbol
python -m pytest -q tests       # 20 tests; tests/ui_smoke.py screenshots every screen
```

Optional: `export ANTHROPIC_API_KEY=...` to run model steps through the API instead of the job queue.

## Publish (GitHub Pages + the cron)

```bash
gh repo create finn --public --source . --push
gh api -X POST repos/{owner}/finn/pages -f build_type=workflow   # Pages served by the Actions workflow
gh secret set ANTHROPIC_API_KEY                                   # optional: model steps for new filings
gh workflow run refresh                                           # first deploy
```

The `refresh` workflow then polls filings every 30 minutes on trading days and rebuilds everything each
evening. The live engine for arbitrary symbols deploys from `render.yaml` (Render → New → Blueprint).

## Repo map

```
finn/            pipeline (sources/, classify, push, research, llm, entities, server)
prompts/         every model prompt, versioned
data/            orgs registry, synthetic network, backfill, committed LLM cache, RSS log
web/             the PWA (no framework, no build step) + data/ read model
tests/           classifier & research unit tests, UI smoke test
docs/            architecture, covering note
```
