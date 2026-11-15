**To:** assessment@enam.com
**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Hello ENAM team,

Here is my submission for the FINN build challenge.

- **Prototype (open on a phone):** https://mayur-agrawal-iitk.github.io/finn/
- **Repository:** https://github.com/mayur-agrawal-iitk/finn
- **AI build history:** &lt;link to the exported Claude Code session&gt;

### What I built

FINN is a phone-first daily brief for an investor, on live NSE/BSE data for a 17-stock portfolio. It is
built around one question: *what changed, what is real, and who do I know who can explain it?*

- **Push.** A ranked brief for the window you pick (24h / 3d / 7d / 30d). The few material filings come
  first as rich cards; routine paperwork is folded into one line. Results cards show Revenue, EBITDA, PBT
  and PAT QoQ and YoY. Management-change cards carry the appointee's profile *from the SEBI-mandated
  brief profile in the filing* and the people in your network most likely to know them. Unusual moves
  follow your own thresholds (net of Nifty if you like), and each one is either tied to a filing or
  flagged as unexplained.
- **Pull.** A research dossier for any NSE symbol, from primary sources only. Snapshot, trajectory,
  balance sheet and cash quality are computed in code. The centre of it is a **promise ledger**: guidance
  from the last four earnings calls, quoted verbatim with page links. Each promise is scored against
  reported numbers where it is numeric; the dossier also shows guidance raised or cut between calls, a
  credibility score, narrative vs numbers, and bull vs bear.
- **Network.** Woven into both: "best placed to explain" on every material card (Page Industries'
  FEMA clarification → its former financial controller, and the lawyer you lean on for foreign-exchange
  rules), seven ranked paths to HDFC Bank's new CEO, an expertise map, and reconnect nudges ("Anup Bagchi,
  HDFC Bank's new MD & CEO, overlapped with Arjun at ICICI Bank" — a classmate you last spoke to 8 months ago).

On real data it already says things worth knowing. Kaynes gets a management-credibility score of 32/100:
it cut FY26 revenue guidance from ₹4,500 cr to ₹4,000 cr and then delivered ₹3,626 cr, while five-year
operating cash flow is negative against ₹977 cr of profit.

### Key decisions and trade-offs

1. **Code first, models last.** Exchange subjects come from a small vocabulary, so rules classify 97.5%
   of filings exactly. Headline numbers come from tables. Promise checks are arithmetic. Models do only
   what needs language understanding: reading transcripts for guidance, reading filings for people,
   and weighing evidence for credibility.
2. **Verification over trust.** Every guidance quote is machine-checked against the transcript; anything
   paraphrased is dropped. The synthesis must cite evidence IDs. Segment targets are never scored
   against company-wide numbers.
3. **Inferred, not asserted, relationships.** The network never claims two people know each other. It
   reports that they overlapped at an employer, for how long and in what roles, and how confident that
   makes it.
4. **A static app plus a cron instead of a server.** The pipeline is the only writer and the browser is a
   reader. That makes the deployed demo free and fast on a phone, and it can't go down. The trade-off is
   that research on a symbol nobody pre-computed needs the live engine (FastAPI, one-click on Render).
5. **Primary sources over convenience.** I used screener.in's numbers and document links, but not its
   pros/cons or AI summaries. I used NSE's published RSS, not its cookie-walled API. I respected robots.txt.

### Architecture (details and diagram in `docs/ARCHITECTURE.md`)

- **Data pipelines.** NSE RSS (polled, then appended to our own log), screener.in, BSE/NSE PDFs and the
  Yahoo chart API go through one polite, cached fetcher. Filings are deduped across exchanges and linked
  by organisation IDs (NSE symbol or registry slug) through a single entity resolver. That resolver also
  links people in filings to the network.
- **Security & privacy.** The investor's network, positions and thresholds stay on the device, and all
  network reasoning runs in the browser. Models only ever read public documents. In production: OIDC
  tenancy, encrypted on-device storage, contacts imported only from the investor's own exports, a
  45-day retention window for public event data, and an insider-information (SEBI PIT) caution whenever
  the best contact works at the listed company.
- **LLMs and agents.** Claude Haiku 5.5 for bulk extraction on retrieved passages (retrieval sends about
  20% of each transcript), and Claude Opus 5.5 for the one judgement step per company per quarter.
  Every call is content-addressed and cached, so the daily refresh only pays for new documents. The whole
  demo cost about $2.70 to compute at API list prices, 97% of it the Opus step. There is
  no autonomous agent in the serving path, on purpose; a tool-using "ask the filings" agent is next.
  *Note:* my build environment had no API key, so the pipeline wrote model steps as self-contained jobs.
  Claude Haiku and Opus workers in my Claude Code session executed them; the outputs were validated and
  imported, and provenance is recorded on each record. With a key, the same prompts go through the API.
- **Cloud.** GitHub Actions runs the pipeline (every 30 minutes on trading days, plus a full build every
  evening) and GitHub Pages serves the app. The live engine is a Docker image. Secrets live only in the
  platform secret stores.

### What I deliberately left out

Chat as the main interface (investors scan, they don't converse); intraday prices; LinkedIn scraping
(the network comes from the investor's own export); broker or news inputs for research; push
notifications on the phone (alerts are evaluated, but not delivered as OS notifications); and user
accounts. The network is synthetic: 36 fictional people at real organisations, built to overlap with the
portfolio.

### Where I'd take it next

1. *Ask the filings*: a tool-using agent over retrieval and quote verification, for questions like
   "what did they say about working capital in the last two calls?"
2. Web-push alerts, and a "since you last looked" window.
3. An exchange data licence for complete filing history, plus XBRL for exact results numbers.
4. Network import from a LinkedIn export and calendar on the device, with relationship strength learned
   from interactions.
5. The Batch API for the evening build (about half the cost), and an eval set for guidance extraction
   built from the verified-quote ledger.

Thank you for the thoughtful brief — I enjoyed building this.

&lt;Your name&gt;
