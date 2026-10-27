#!/usr/bin/env python3
"""Scan web-games.json play pages for embeddable game iframe URLs.

For each game entry, fetches the game's play page and looks for an <iframe>
whose src looks like the game bundle itself (not ads/players shells).
Results are merged back into web-games.json as an optional "iframe_url"
field; games without a findable iframe are left untouched. HTML responses
are cached in tools/games-local-test/pagecache/ so re-runs are cheap and
polite to the hosts.

Output summary goes to stderr; per-game findings go to stdout.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAMES_JSON = HERE.parent / "web-games.json"
CACHE_DIR = HERE / "games-local-test" / "pagecache"
DELAY_SECONDS = 1.5
TIMEOUT_SECONDS = 30

# iframe srcs that are plausibly the game itself. The PBS sites use
# "GamePlayer_frame"; springroll-tc is PBS's actual game host. Generic
# patterns cover other providers (html5 game paths, .html bundles).
BUNDLE_HINTS = (
    "gameplayer_frame",
    "springroll",
    "games-embed",
    "/games/embed",
    "embedgame",
    "game_loader",
    "gamelab",
    "index.html",
    "/game/",
    "unitywebgl",
    "html5",
    "/content/",
)

IFRAME_RE = re.compile(
    r"<iframe\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*>",
    re.IGNORECASE,
)

# PBS Kids pages are client-rendered (Next.js): the game iframe is not in the
# HTML, but the page data carries the springroll release bundle URL directly.
SPRINGROLL_RE = re.compile(
    r'"hash":"[0-9a-f]{40}","url":"(https://springroll[^\"]+/index\.html)"'
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def cache_path(url: str) -> Path:
    import hashlib

    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".html")


def fetch(url: str, *, force: bool = False) -> str | None:
    cp = cache_path(url)
    if cp.exists() and not force:
        return cp.read_text(errors="replace")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - report, never crash the scan
        print(f"  !! fetch failed: {exc}", file=sys.stderr)
        return None
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(body)
    time.sleep(DELAY_SECONDS)
    return body


def absolutize(src: str, page_url: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        base = page_url.split("/")[2]
        return f"https://{base}{src}"
    if src.startswith("http"):
        return src
    # relative to page dir
    base = page_url.rsplit("/", 1)[0]
    return f"{base}/{src}"


def find_iframe_urls(html: str, page_url: str) -> list[str]:
    found: list[str] = []
    for match in IFRAME_RE.finditer(html):
        attrs = match.group(0)
        src = absolutize(match.group(1), page_url)
        hints = [h for h in BUNDLE_HINTS if h in src.lower() or h in attrs.lower()]
        if hints or "game" in attrs.lower():
            found.append(src)
    # de-dup, keep order
    return list(dict.fromkeys(found))


def find_springroll_url(html: str) -> str | None:
    match = SPRINGROLL_RE.search(html)
    return match.group(1) if match else None


def main() -> int:
    data = json.loads(GAMES_JSON.read_text())
    changed = 0
    for provider in data:
        print(f"== {provider['name']}", file=sys.stderr)
        for item in provider["items"]:
            url = item["url"]
            html = fetch(url)
            if html is None:
                print(f"  {item['name']}: FETCH FAILED", file=sys.stderr)
                continue
            springroll = find_springroll_url(html)
            if springroll is not None:
                old = item.get("iframe_url")
                item["iframe_url"] = springroll
                if old != springroll:
                    changed += 1
                print(f"  {item['name']}: {springroll}", file=sys.stderr)
                continue
            candidates = find_iframe_urls(html, url)
            if not candidates:
                print(f"  {item['name']}: no iframe found", file=sys.stderr)
                continue
            best = candidates[0]
            old = item.get("iframe_url")
            item["iframe_url"] = best
            if old != best:
                changed += 1
            extra = f" (+{len(candidates)-1} more)" if len(candidates) > 1 else ""
            print(f"  {item['name']}: {best}{extra}", file=sys.stderr)
    GAMES_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {GAMES_JSON}; updated {changed} entries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
