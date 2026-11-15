# How this was built — a guide to the AI build history

FINN was built in one Claude Code session (Claude Opus 5.5 as the lead, plus Claude Haiku and Opus worker
agents). The full session export is the primary record; this page lists the turns worth looking at.

## How the problem was broken down

1. **Read the brief and the reference, then probe the sources before designing.** We checked which
   sources actually answer from a script. screener.in and Yahoo did. NSE's JSON API sits behind a bot
   wall. NSE's RSS feed works, but only holds ~130 items. That shaped the design: RSS plus our own log,
   with screener's recent filings as backfill.
2. **Scan 50 candidate companies for real events in the window** (8–15 Nov 2026) before choosing the
   portfolio: a bank CEO transition, Q2 results, a FEMA clarification, defence orders, two EMS JVs.
3. **Deterministic spine first** (fetch, classify, results numbers, research analytics), then model steps
   only where language understanding is needed, then the on-device network, then the UI.
4. **Verify everything visually.** A headless-Chromium smoke test loads every screen at phone size, fails
   on any JavaScript error, and saves screenshots that were reviewed after each iteration.

## Course corrections (what went wrong and what changed)

| What happened | What we did |
|---|---|
| A plan to use browser cookies on NSE's JSON API was refused by the session's safety layer. | Respected it. We use NSE's published RSS and screener.in instead, and say so in the docs. |
| NSE's archive reset Python `requests` connections, and silently dropped user agents containing a URL. | Moved to `httpx` and a plain identifying UA. No browser spoofing. |
| The first classifier pass misfired on real titles: "Infosys Prize **Research**ers" read as litigation, "Dis**closure**" as a closure order, a ₹1.6 lakh penalty as material. | Fixed each one and locked them in as regression tests (`tests/test_classify.py`). |
| A scripted patch wrote literal backspace characters into nine regexes (`\b` became `\x08`). | Found by inspecting why a fix didn't apply; repaired, and code edits moved to file tools only. |
| No usable API key in the build environment. | Designed a job queue: each model step is written as a self-contained prompt + schema, executed by Haiku/Opus workers, validated (`llm-check`), imported with provenance. The API path uses the same prompts. |
| HDFC Bank's CEO approval filing had no profile, so "who knows the new CEO" returned nothing. | Traced it to the earlier notice (found on NSE's archive), added a 60-day profile look-back and richest-record merge by name. |
| "CEO (Helicopter Complex)" scored like a company CEO. | Re-calibrate from the extracted roles: division-level roles drop to "senior"; bundled board outcomes let results lead. |
| The synthesis workers reported input bugs while doing their jobs: a stale consolidated page (AAVAS stopped at FY24), negative "financing margins" for banks, drift comparing unrelated items, segment targets scored against company totals, duplicate transcripts, a mislabelled call. | Fixed all six in code, then re-ran synthesis **only for the 17 companies whose inputs changed** — the content-addressed cache made that a precise, cheap re-run. |
| The second round's workers reported more: context passages that were cover letters or safe-harbour text, and drift groups that still mixed a company target with segment targets (₹56,000 cr vs ₹1,200 cr), plus a 1.5% → 1.4% credit-cost revision labelled "held". | Context now keeps only substantive, number-bearing management commentary. Drift drops any group whose numbers differ more than 1.4× within one call, uses relative thresholds, and says "lowered" with metric polarity (lower credit cost is good). The remaining round-2 workers were stopped, since their inputs were about to change, and a final round re-ran all 20. |
| A junior contact out-ranked a regional head as the path to a new MD. | Added a seniority-gap penalty to inferred links; the explanation now says "though several levels apart". |
| Creating the public GitHub repo from the session was blocked as an outward-facing action. | Everything is committed locally; publishing is one command for the owner (README → Publish). |

## What was accepted vs rewritten

- Worker outputs were **never accepted on trust**. They had to pass schema validation; every guidance
  quote was checked against the transcript (477 in the final ledger, 0 dropped); numeric promises were re-scored by code.
  Synthesis had to cite IDs that exist in its input.
- Where model judgement and arithmetic disagreed, arithmetic won: computed checks are inputs to the
  synthesis, not suggestions.
