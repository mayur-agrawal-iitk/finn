"""Primary documents: download once (filings are immutable), extract page text once.

Page numbers are kept so every downstream claim can cite `doc + page`.
"""
from __future__ import annotations

import hashlib
import io
import json
import re

from .config import CACHE
from .net import fetcher

TEXT_DIR = CACHE / "text"
TEXT_DIR.mkdir(parents=True, exist_ok=True)


def doc_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def pdf_pages(url: str, max_pages: int | None = None) -> list[str]:
    """Return a list of page texts. Cached on disk by URL hash."""
    out = TEXT_DIR / f"{doc_id(url)}.json"
    if out.exists():
        pages = json.loads(out.read_text(encoding="utf-8"))
        return pages[:max_pages] if max_pages else pages
    raw = fetcher().get(url, ttl=None, timeout=90)
    if not raw.startswith(b"%PDF"):
        pages = [_clean(raw.decode("utf-8", errors="replace"))]
    else:
        pages = _extract(raw, max_pages)
    if not max_pages:
        out.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def _extract(raw: bytes, max_pages: int | None) -> list[str]:
    import pdfplumber  # imported lazily; heavy

    pages = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for i, p in enumerate(pdf.pages):
            if max_pages and i >= max_pages:
                break
            try:
                pages.append(_clean(p.extract_text() or ""))
            except Exception:
                pages.append("")
    return pages


def _clean(t: str) -> str:
    t = t.replace(" ", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def is_scanned(pages: list[str]) -> bool:
    """Image-only PDFs extract to (almost) nothing — flag them rather than guess."""
    return sum(len(p) for p in pages) < 200 * max(1, len(pages)) * 0.2
