"""FINN command line.

  python -m finn build            # full refresh: prices, filings, research, web/data/*.json
  python -m finn push             # push side only (prices + filings) — what the 15-min cron runs
  python -m finn research SYMBOL  # build one research dossier (any NSE symbol)
  python -m finn serve            # FastAPI: static app + live research API
  python -m finn llm-pending      # list model tasks waiting for a worker (no API key configured)
  python -m finn llm-import DIR   # import offline-batch outputs into the content-addressed cache
  python -m finn llm-cost         # cost ledger
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="finn")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--skip-research", action="store_true")
    sub.add_parser("push")
    r = sub.add_parser("research")
    r.add_argument("symbol")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    sub.add_parser("llm-pending")
    i = sub.add_parser("llm-import")
    i.add_argument("dir")
    i.add_argument("--provenance", default="offline-batch")
    sub.add_parser("llm-cost")
    e = sub.add_parser("llm-export")
    e.add_argument("--batches", type=int, default=6)
    e.add_argument("--task", default=None)
    c = sub.add_parser("llm-check")
    c.add_argument("dir")
    a = ap.parse_args(argv)

    if a.cmd in ("build", "push"):
        from .build import build
        build(research=(a.cmd == "build" and not a.skip_research))
    elif a.cmd == "research":
        from .build import write_research
        d = write_research(a.symbol.upper())
        print(json.dumps({k: d.get(k) for k in ("symbol", "name", "status")}, indent=1))
    elif a.cmd == "serve":
        import uvicorn
        uvicorn.run("finn.server:app", host=a.host, port=a.port, reload=False)
    elif a.cmd == "llm-pending":
        from . import llm
        jobs = llm.pending_jobs()
        for j in jobs:
            print(f"{j['task']:12} {j['model']:18} {j['key']}  {j.get('label','')}")
        print(f"{len(jobs)} pending")
    elif a.cmd == "llm-import":
        from pathlib import Path
        from . import llm
        ok, problems = llm.import_results(Path(a.dir), a.provenance)
        print(f"imported {ok}")
        for p in problems:
            print("  !", p)
    elif a.cmd == "llm-export":
        from . import llm
        print(json.dumps(llm.export_jobs(a.batches, a.task), indent=1))
    elif a.cmd == "llm-check":
        from pathlib import Path
        from . import llm
        bad = llm.check_outputs(Path(a.dir))
        for b in bad:
            print("  !", b)
        print("all valid" if not bad else f"{len(bad)} problems")
    elif a.cmd == "llm-cost":
        from . import llm
        print(json.dumps(llm.ledger_summary(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
