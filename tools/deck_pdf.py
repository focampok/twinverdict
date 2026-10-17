"""Export the pitch deck to one 16:9 page per section.

The on-screen deck is not modified. Print layout comes from netlify-visual/print.css
(media="print"). The Gantt playhead is JS, not CSS, so this script runs Play to the
end and only then prints, which is the recording's final frame.

    uv run python tools/deck_pdf.py
    uv run python tools/deck_pdf.py --local
    uv run python tools/deck_pdf.py --url http://127.0.0.1:8766

Writes video/out/twinverdict_pitch.pdf (gitignored). Roadmap is dropped when that
slide is empty or its content is taller than the page.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import threading
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DECK_DIR = ROOT / "netlify-visual"
OUT = ROOT / "video" / "out" / "twinverdict_pitch.pdf"
PUBLISHED = "https://info-twinverdict.focampo.com"

LOADED = """() => {
  const status = document.querySelector("#results-status");
  const amd = document.querySelector("#amd-status");
  const summary = document.querySelector("#seed-summary");
  const lane = document.querySelector("#lane-baseline");
  return Boolean(
    status && status.hidden
    && amd && amd.hidden
    && summary && summary.textContent.trim()
    && lane && lane.querySelector("rect")
  );
}"""

ROADMAP = """() => {
  const slide = document.querySelector("#roadmap");
  if (!slide) return "missing";
  const text = (slide.innerText || "").replace(/\\s+/g, " ").trim();
  const box = slide.getBoundingClientRect();
  const inner = slide.querySelector(".slide-inner");
  const innerBox = inner ? inner.getBoundingClientRect() : null;
  const empty = text.length === 0;
  const clipped = slide.scrollHeight > slide.clientHeight + 2
    || slide.scrollWidth > slide.clientWidth + 2
    || (innerBox !== null && (
      innerBox.bottom > box.bottom + 1 || innerBox.top < box.top - 1
      || innerBox.right > box.right + 1
    ));
  if (empty || clipped) {
    slide.remove();
    return empty ? "empty" : "clipped";
  }
  return "kept";
}"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the TwinVerdict pitch deck to PDF.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Serve netlify-visual/ instead of the published deck.",
    )
    parser.add_argument("--url", default=None, help=f"Deck URL (default: {PUBLISHED}).")
    args = parser.parse_args()
    if args.local and args.url:
        parser.error("--local and --url are mutually exclusive")
    return args


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def _serve_local() -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(_QuietHandler, directory=str(DECK_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/"


def _finish_gantt(page: Page) -> str:
    """Run the playhead to the end of the window. Returns the final label."""
    play = page.locator("#play")
    if play.is_disabled():
        return page.locator("#playhead-label").inner_text()
    play.click()
    page.wait_for_function(
        "() => document.querySelector('#play').textContent.trim() === 'Pause'",
        timeout=2_000,
    )
    page.wait_for_function(
        "() => document.querySelector('#play').textContent.trim() === 'Play'",
        timeout=20_000,
    )
    return page.locator("#playhead-label").inner_text()


def export_pdf(url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.goto(url, wait_until="networkidle")
        page.wait_for_function(LOADED, timeout=20_000)
        label = _finish_gantt(page)
        page.emulate_media(media="print")
        roadmap = page.evaluate(ROADMAP)
        page.pdf(
            path=str(dest),
            width="1920px",
            height="1080px",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        browser.close()
    return f"{label}; roadmap {roadmap}"


def main() -> None:
    args = _parse_args()
    server: http.server.ThreadingHTTPServer | None = None
    if args.local:
        server, url = _serve_local()
    else:
        url = args.url or PUBLISHED
    try:
        note = export_pdf(url, OUT)
    finally:
        if server is not None:
            server.shutdown()
    print(f"{OUT.relative_to(ROOT)}  ({note})")


if __name__ == "__main__":
    main()
