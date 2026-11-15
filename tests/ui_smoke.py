"""UI smoke test: load every screen at phone size, fail on any JS error, save screenshots.

  python tests/ui_smoke.py <screenshot_dir>

Needs `pip install playwright && python -m playwright install chromium`.
"""
from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parent.parent / "web"


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events = json.loads((WEB / "data" / "events.json").read_text(encoding="utf-8"))
    mat = sorted(events, key=lambda e: -e["score"])
    mgmt = next((e for e in events if e["category"] == "management_change" and any("CEO" in p["role"] or "Chief Executive" in p["role"] for p in e.get("people", []))), mat[0])
    routes = [
        ("brief", "#/brief"), ("brief-7d", "#/brief"), ("event", f"#/e/{mat[0]['id']}"), ("event-mgmt", f"#/e/{mgmt['id']}"),
        ("research", "#/research"), ("company", "#/r/KAYNES"), ("company-promises", "#/r/KAYNES?tab=promises"),
        ("company-numbers", "#/r/KAYNES?tab=numbers"), ("company-cash", "#/r/KAYNES?tab=cash"), ("company-people", "#/r/KAYNES?tab=people"),
        ("bank", "#/r/HDFCBANK?tab=balance"), ("missing", "#/r/ZZZZ"),
        ("network", "#/network"), ("network-ask", "#/network?q=Anup%20Bagchi"), ("network-theme", "#/network?q=specialty%20chemicals"),
        ("person", "#/p/p12"), ("watch", "#/watch"),
    ]
    srv, port = serve()
    errors: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.goto(f"http://127.0.0.1:{port}/index.html#/brief")
        page.wait_for_selector(".view", timeout=15000)
        for name, h in routes:
            if name == "brief-7d":
                page.evaluate("location.hash = '#/brief'")
                page.wait_for_timeout(300)
                btn = page.query_selector('[data-window="7d"]')
                if btn:
                    btn.click()
            else:
                page.evaluate(f"location.hash = {json.dumps(h)}")
            page.wait_for_timeout(700)
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
            page.screenshot(path=str(out / f"{name}-top.png"), full_page=False)
            text = page.inner_text("#app")
            print(f"{name:18} {len(text):6} chars")
        b.close()
    srv.shutdown()
    errors = [e for e in errors if "fonts.g" not in e and "favicon" not in e and "api/health" not in e and "404" not in e]
    for e in errors:
        print("  !", e)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "screens"))
