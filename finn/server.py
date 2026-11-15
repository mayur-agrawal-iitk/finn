"""Live engine: the same static app, plus on-demand research for ANY NSE symbol.

  GET /api/research/{symbol}   -> dossier (cached on disk; built on first request)
  GET /api/health              -> status, model availability, cost to date
  /                            -> the PWA (web/)

The static deployment (GitHub Pages) serves pre-built dossiers; this server is what lets a
user point FINN at a company nobody pre-computed. Deterministic sections return in seconds;
model sections are served from the content-addressed cache or computed when a key is set.
"""
from __future__ import annotations

import json
import re
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import llm, research
from .config import WEB, WEB_DATA

app = FastAPI(title="FINN", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
_locks: dict[str, threading.Lock] = {}
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
FRESH = 12 * 3600


@app.get("/api/health")
def health():
    return {"ok": True, "llm_api": llm.api_available(), "llm": llm.ledger_summary()}


@app.get("/api/research/{symbol}")
def get_research(symbol: str, refresh: bool = False):
    sym = symbol.upper().strip()
    if not SYMBOL.match(sym):
        raise HTTPException(400, "not a valid NSE symbol")
    path = WEB_DATA / "research" / f"{sym}.json"
    if path.exists() and not refresh and time.time() - path.stat().st_mtime < FRESH:
        return json.loads(path.read_text(encoding="utf-8"))
    lock = _locks.setdefault(sym, threading.Lock())
    with lock:  # one build per symbol at a time; concurrent callers wait for it
        d = research.dossier(sym)
        if d.get("status") != "ok":
            raise HTTPException(404, f"no reported financials found for {sym}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")
        return d


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
