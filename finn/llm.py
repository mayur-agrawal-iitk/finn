"""LLM layer: model routing, content-addressed caching, schema-validated JSON, cost ledger.

Design rules
  * Deterministic code first. A model is called only for language understanding that rules
    cannot do (reading a transcript for guidance, a filing for a person's career).
  * Route by difficulty: bulk extraction -> Claude Haiku 5.5 ($0.10 / $0.50 per MTok);
    judgement over many facts -> Claude Opus 5.5. Nothing else.
  * Every call is keyed by sha256(task, prompt version, model, inputs). Filings are immutable,
    so a cached answer is valid forever and the daily refresh costs ~nothing.
  * Outputs are constrained with `output_config.format` (JSON schema) and re-validated here.
  * The investor's private network is NEVER sent to a model (see docs/ARCHITECTURE.md).

When no API key is configured, a task is written to `.cache/llm_jobs/` as a self-contained
job (rendered prompt + schema). Those jobs can be executed by any offline batch worker and
imported with `python -m finn llm-import <dir>`; this is how the demo cache in
`data/llm_cache/` was produced (provenance is recorded in every cached record).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .config import CACHE, DATA, PROMPTS

LLM_CACHE = DATA / "llm_cache"          # committed: derived from public filings only
JOBS = CACHE / "llm_jobs"
LEDGER = CACHE / "llm_ledger.jsonl"
for p in (LLM_CACHE, JOBS):
    p.mkdir(parents=True, exist_ok=True)

PRICES = {  # USD per million tokens (input, output)
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


@dataclass(frozen=True)
class Task:
    name: str
    model: str
    effort: str
    max_tokens: int
    prompt: str          # file under prompts/
    version: str         # bump to invalidate cached answers when the prompt changes


TASKS = {
    "classify":   Task("classify",   "claude-haiku-5-5", "low",    600,   "classify.md",   "v1"),
    "event_brief": Task("event_brief", "claude-haiku-5-5", "low",  1200,  "event_brief.md", "v1"),
    "people":     Task("people",     "claude-haiku-5-5", "medium", 3000,  "people.md",     "v1"),
    "results":    Task("results",    "claude-haiku-5-5", "medium", 2000,  "results.md",    "v1"),
    "guidance":   Task("guidance",   "claude-haiku-5-5", "medium", 6000,  "guidance.md",   "v1"),
    "synthesis":  Task("synthesis",  "claude-opus-5-5",  "high",   12000, "synthesis.md",  "v1"),
}


def _schema(task: str) -> dict:
    from . import schemas
    return schemas.SCHEMAS[task]


def _render(task: Task, inputs: dict) -> tuple[str, str]:
    """Prompt files have a system part and a user part separated by a line '---USER---'."""
    raw = (PROMPTS / task.prompt).read_text(encoding="utf-8")
    system, user = raw.split("---USER---", 1)
    payload = json.dumps(inputs, ensure_ascii=False, indent=1, sort_keys=True)
    return system.strip(), user.strip().replace("{{INPUT}}", payload)


def cache_key(task_name: str, inputs: dict) -> str:
    t = TASKS[task_name]
    blob = json.dumps({"t": t.name, "v": t.version, "m": t.model, "i": inputs}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def cached(task_name: str, inputs: dict) -> dict | None:
    p = LLM_CACHE / task_name / f"{cache_key(task_name, inputs)}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["output"]
    return None


def _store(task_name: str, key: str, output: dict, meta: dict) -> None:
    d = LLM_CACHE / task_name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps({"output": output, "meta": meta}, ensure_ascii=False, indent=1), encoding="utf-8")


_API_DISABLED = False  # flipped on the first authentication failure; the run then queues jobs instead


def api_available() -> bool:
    return (not _API_DISABLED) and bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("FINN_LLM", "on") != "off"


def run(task_name: str, inputs: dict, *, label: str = "") -> dict | None:
    """Return the task output, from cache or the API; None if it could not be produced now."""
    hit = cached(task_name, inputs)
    if hit is not None:
        return hit
    task = TASKS[task_name]
    key = cache_key(task_name, inputs)
    system, user = _render(task, inputs)
    if api_available():
        out = _call(task, key, system, user, label)
        if out is not None or api_available():
            return out
    job = {"key": key, "task": task_name, "label": label, "model": task.model, "effort": task.effort,
           "system": system, "user": user, "schema": _schema(task_name), "inputs_hash": key}
    (JOBS / f"{task_name}-{key}.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    return None


def _call(task: Task, key: str, system: str, user: str, label: str) -> dict | None:
    import anthropic

    client = anthropic.Anthropic()
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=task.model,
            max_tokens=task.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": task.effort, "format": {"type": "json_schema", "schema": _schema(task.name)}},
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
        global _API_DISABLED
        _API_DISABLED = True
        print(f"  ! llm disabled for this run ({type(exc).__name__}); tasks will be queued as jobs")
        return None
    except anthropic.RateLimitError:
        time.sleep(20)
        return None
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        print(f"  ! llm {task.name} {label}: {exc}")
        return None
    if resp.stop_reason in ("refusal", "max_tokens"):
        print(f"  ! llm {task.name} {label}: stop_reason={resp.stop_reason}")
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        return None
    u = resp.usage
    pin, pout = PRICES.get(task.model, (0, 0))
    cost = (u.input_tokens * pin + u.output_tokens * pout) / 1e6
    meta = {"model": task.model, "effort": task.effort, "provenance": "anthropic-api", "label": label,
            "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "usd": round(cost, 5),
            "seconds": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _store(task.name, key, out, meta)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"task": task.name, **meta}) + "\n")
    return out


def validate(task_name: str, output: dict) -> list[str]:
    """Minimal JSON-schema check (required keys, types, enums) — no extra dependency."""
    errs: list[str] = []

    def walk(node, schema, path):
        t = schema.get("type")
        types = t if isinstance(t, list) else [t] if t else []
        pytypes = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool, "null": type(None)}
        if types and not any(isinstance(node, pytypes[x]) for x in types if x in pytypes):
            errs.append(f"{path}: expected {types}, got {type(node).__name__}")
            return
        if "enum" in schema and node not in schema["enum"]:
            errs.append(f"{path}: {node!r} not in enum")
        if isinstance(node, dict):
            for r in schema.get("required", []):
                if r not in node:
                    errs.append(f"{path}.{r}: missing")
            for k, v in node.items():
                if k in schema.get("properties", {}):
                    walk(v, schema["properties"][k], f"{path}.{k}")
        if isinstance(node, list) and "items" in schema:
            for i, v in enumerate(node):
                walk(v, schema["items"], f"{path}[{i}]")

    walk(output, _schema(task_name), "$")
    return errs


def import_results(directory: Path, provenance: str) -> tuple[int, list[str]]:
    """Import offline-batch outputs: files named <task>-<key>.out.json next to the job files."""
    ok, problems = 0, []
    for out_file in sorted(Path(directory).glob("*.out.json")):
        stem = out_file.name[: -len(".out.json")]
        job_file = JOBS / f"{stem}.json"
        if not job_file.exists():
            problems.append(f"{out_file.name}: no matching job")
            continue
        job = json.loads(job_file.read_text(encoding="utf-8"))
        try:
            output = json.loads(out_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{out_file.name}: bad json {exc}")
            continue
        errs = validate(job["task"], output)
        if errs:
            problems.append(f"{out_file.name}: {errs[:3]}")
            continue
        _store(job["task"], job["key"], output, {"model": job["model"], "provenance": provenance, "label": job.get("label", ""),
                                                 "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **estimate(job, output)})
        ok += 1
    return ok, problems


def pending_jobs() -> list[dict]:
    out = []
    for p in sorted(JOBS.glob("*.json")):
        job = json.loads(p.read_text(encoding="utf-8"))
        if cached_by_key(job["task"], job["key"]) is None:
            out.append(job)
    return out


def latest(task_name: str, label: str) -> dict | None:
    """Most recent cached record for a label (e.g. 'KAYNES synthesis') regardless of inputs."""
    best = None
    for p in (LLM_CACHE / task_name).glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("meta", {}).get("label") == label and (best is None or rec["meta"].get("at", "") > best["meta"].get("at", "")):
            best = rec
    return best


def cached_by_key(task_name: str, key: str) -> dict | None:
    p = LLM_CACHE / task_name / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8"))["output"] if p.exists() else None


def ledger_summary() -> dict:
    tot = {"calls": 0, "usd": 0.0, "input_tokens": 0, "output_tokens": 0, "est_usd": 0.0, "est_input_tokens": 0, "by_task": {}}
    for d in LLM_CACHE.glob("*/*.json"):
        meta = json.loads(d.read_text(encoding="utf-8")).get("meta", {})
        tot["calls"] += 1
        tot["usd"] += meta.get("usd", 0) or 0
        tot["input_tokens"] += meta.get("input_tokens", 0) or 0
        tot["output_tokens"] += meta.get("output_tokens", 0) or 0
        est = meta.get("usd") or meta.get("est_usd") or 0
        tot["est_usd"] += est
        tot["est_input_tokens"] += meta.get("input_tokens") or meta.get("est_input_tokens") or 0
        t = tot["by_task"].setdefault(d.parent.name, {"n": 0, "est_usd": 0.0})
        t["n"] += 1
        t["est_usd"] = round(t["est_usd"] + est, 4)
    tot["usd"] = round(tot["usd"], 4)
    tot["est_usd"] = round(tot["est_usd"], 3)
    return tot


def backfill_estimates() -> int:
    """Add token/cost estimates to cached records produced offline before estimates were recorded."""
    n = 0
    for jf in JOBS.glob("*.json"):
        job = json.loads(jf.read_text(encoding="utf-8"))
        p = LLM_CACHE / job["task"] / f"{job['key']}.json"
        if not p.exists():
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        if "est_usd" in rec["meta"] or "usd" in rec["meta"]:
            continue
        rec["meta"].update(estimate(job, rec["output"]))
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    return n


def estimate(job: dict, output: dict) -> dict:
    """Token/cost estimate at API list prices for an output produced offline (~3.8 chars per token)."""
    tin = int((len(job["system"]) + len(job["user"]) + len(json.dumps(job["schema"]))) / 3.8)
    tout = int(len(json.dumps(output, ensure_ascii=False)) / 3.8 * (2.0 if TASKS[job["task"]].model == "claude-opus-5-5" else 1.3))
    pin, pout = PRICES.get(job["model"], (0, 0))
    return {"est_input_tokens": tin, "est_output_tokens": tout, "est_usd": round((tin * pin + tout * pout) / 1e6, 5)}


def export_jobs(batches: int, task: str | None = None) -> dict:
    """Write pending jobs as readable prompt files, split into balanced batches for offline workers."""
    out = CACHE / "llm_export"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        old.unlink()
    jobs = [j for j in pending_jobs() if task is None or j["task"] == task]
    jobs.sort(key=lambda j: (j["task"], j.get("label", "")))
    groups: list[list] = [[] for _ in range(max(1, batches))]
    sizes = [0] * len(groups)
    for j in sorted(jobs, key=lambda j: -len(j["user"])):
        i = sizes.index(min(sizes))
        groups[i].append(j)
        sizes[i] += len(j["user"])
    manifest = {}
    for gi, g in enumerate(groups):
        names = []
        for j in g:
            stem = f"{j['task']}-{j['key']}"
            md = "\n".join([
                f"# JOB {stem}", "", f"label: {j.get('label', '')}", f"model tier: {j['model']}", "",
                "## SYSTEM", "", j["system"], "", "## USER", "", j["user"], "",
                "## OUTPUT JSON SCHEMA", "", "```json", json.dumps(j["schema"], indent=1), "```", ""])
            (out / f"{stem}.md").write_text(md, encoding="utf-8")
            names.append(stem)
        manifest[f"batch{gi + 1}"] = {"jobs": names, "chars": sizes[gi]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {k: {"n": len(v["jobs"]), "chars": v["chars"]} for k, v in manifest.items()}


def check_outputs(directory: Path) -> list[str]:
    bad = []
    for f in sorted(Path(directory).glob("*.out.json")):
        stem = f.name[: -len(".out.json")]
        job_file = JOBS / f"{stem}.json"
        if not job_file.exists():
            bad.append(f"{f.name}: unknown job")
            continue
        job = json.loads(job_file.read_text(encoding="utf-8"))
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            bad.append(f"{f.name}: invalid JSON ({exc})")
            continue
        errs = validate(job["task"], data)
        if errs:
            bad.append(f"{f.name}: {errs[:4]}")
    return bad
