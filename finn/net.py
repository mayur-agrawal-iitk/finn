"""A small, polite HTTP layer: per-host rate limiting, retries and an on-disk cache.

Every pipeline fetch goes through here so that (a) we never hammer a public source,
(b) re-running the pipeline is free when nothing changed, and (c) runs are reproducible.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import CACHE, HOST_INTERVAL, USER_AGENT


class Fetcher:
    def __init__(self, cache_dir: Path = CACHE / "http"):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # httpx rather than requests: NSE's archive edge resets requests' connections but serves
        # standard clients (curl, urllib, httpx) normally.
        self.session = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self.stats = {"network": 0, "cache": 0}

    # -- cache ---------------------------------------------------------------
    def _paths(self, url: str) -> tuple[Path, Path]:
        h = hashlib.sha1(url.encode()).hexdigest()
        return self.cache_dir / f"{h}.body", self.cache_dir / f"{h}.meta"

    def _cached(self, url: str, ttl: float | None) -> bytes | None:
        body, meta = self._paths(url)
        if not body.exists() or not meta.exists():
            return None
        if ttl is not None:
            fetched = json.loads(meta.read_text())["fetched"]
            if time.time() - fetched > ttl:
                return None
        return body.read_bytes()

    def _store(self, url: str, content: bytes, status: int, ctype: str) -> None:
        body, meta = self._paths(url)
        body.write_bytes(content)
        meta.write_text(json.dumps({"url": url, "fetched": time.time(), "status": status, "content_type": ctype}))

    # -- politeness ------------------------------------------------------------
    def _wait_turn(self, host: str) -> None:
        gap = HOST_INTERVAL.get(host, 0.5)
        with self._lock:
            now = time.time()
            wait = self._last.get(host, 0) + gap - now
            self._last[host] = max(now, self._last.get(host, 0) + gap)
        if wait > 0:
            time.sleep(wait)

    # -- public ----------------------------------------------------------------
    def get(self, url: str, ttl: float | None = 6 * 3600, retries: int = 3, timeout: float = 45) -> bytes:
        """GET with cache. ttl=None means 'cache forever' (immutable documents like PDFs)."""
        hit = self._cached(url, ttl)
        if hit is not None:
            self.stats["cache"] += 1
            return hit
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._wait_turn(host)
            try:
                r = self.session.get(url, timeout=timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"{r.status_code} for {url}")
                r.raise_for_status()
                self.stats["network"] += 1
                self._store(url, r.content, r.status_code, r.headers.get("content-type", ""))
                return r.content
            except Exception as exc:  # network flakiness: back off and retry
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"fetch failed: {url}: {last_exc}")

    def text(self, url: str, ttl: float | None = 6 * 3600) -> str:
        return self.get(url, ttl).decode("utf-8", errors="replace")

    def json(self, url: str, ttl: float | None = 6 * 3600):
        return json.loads(self.get(url, ttl))


_default: Fetcher | None = None


def fetcher() -> Fetcher:
    global _default
    if _default is None:
        _default = Fetcher()
    return _default
