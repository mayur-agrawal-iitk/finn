"""Entity resolution: map free-text organisation names (from filings, profiles, contacts) to stable ids.

Listed companies resolve to their NSE symbol; everything else to a slug from data/orgs.json.
The same ids are used by the public pipeline (people in filings) and by the private network
on the client, so the join "who in my network worked where this new CFO worked" is an exact
id match — never a model call over personal data.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .config import DATA
from .util import norm_org


@lru_cache(maxsize=1)
def _registry() -> tuple[dict[str, str], dict[str, dict]]:
    orgs = json.loads((DATA / "orgs.json").read_text(encoding="utf-8"))
    alias: dict[str, str] = {}
    for oid, o in orgs.items():
        for a in [o["name"], *o.get("aliases", [])]:
            alias[norm_org(a)] = oid
    try:
        from .sources.nse import equity_master
        for m in equity_master():
            alias.setdefault(norm_org(m["name"]), m["symbol"])
    except Exception:
        pass
    return alias, orgs


def resolve(name: str | None) -> str | None:
    if not name:
        return None
    alias, _ = _registry()
    key = norm_org(name)
    if key in alias:
        return alias[key]
    # tolerate suffixes like "ICICI Bank (Retail Banking)" or "Tata Motors, Pune"
    base = norm_org(re.split(r"[(,;/]", name)[0])
    if base in alias:
        return alias[base]
    # prefix match on a distinctive first token pair
    toks = base.split()
    if len(toks) >= 2:
        pref = " ".join(toks[:2])
        cands = {v for k, v in alias.items() if k.startswith(pref)}
        if len(cands) == 1:
            return cands.pop()
    return None


def org_meta(org_id: str) -> dict:
    _, orgs = _registry()
    return orgs.get(org_id, {})
