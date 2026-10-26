"""Loopback HTTP server for the web-based parent UI.

Single-threaded by design: all requests are served from one dedicated thread,
which owns its own SQLite connection (the storage layer's thread-confinement
contract). The server binds 127.0.0.1 only. Per the owner, the parent gesture
is the only gate for now; no token is required.
"""

import http.server
import re
import threading
import urllib.parse
from dataclasses import dataclass
from html import escape
from uuid import UUID

PARENT_CSS = b"""
body { background: #0f0f10; color: #ffb000; font-family: sans-serif;
       font-size: 30px; padding: 24px; margin: 0; }
h1 { font-size: 40px; }
a { color: #ffb000; }
.badge { border: 2px solid #8a8a8a; color: #ddd; padding: 2px 10px;
         border-radius: 4px; font-size: 22px; }
li { margin: 14px 0; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.ptile { height: 300px; border-radius: 36px; display: flex; align-items: center;
         justify-content: center; font-size: 44px; font-weight: 800;
         color: #1b1b2f; text-decoration: none; }
.portal { background: #ffd43b; color: #1b1b2f; padding: 20px;
          border-radius: 12px; margin: 16px 0; }
.wifi-form { margin: 20px 0; font-size: 26px; }
.wifi-form select, .wifi-form input { font-size: 26px; padding: 10px; }
.wifi-form button { font-size: 28px; padding: 12px 24px; margin-top: 14px; }
.msg { color: #8ac926; }
.err { color: #ff6b6b; }
"""


@dataclass(frozen=True)
class ReviewRow:
    """Display projection of one catalog entry for the review page."""

    game_id: str
    name: str
    status: str
    rating: int | None


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width'>"
        f"<title>{escape(title)}</title>"
        f"<style>{PARENT_CSS.decode()}</style></head>"
        f"<body><h1>{escape(title)}</h1>{body}</body></html>"
    )


def render_menu() -> str:
    tiles = (
        ("/review", "#4dabf7", "Review"),
        ("/wifi", "#20c997", "Wi-Fi"),
        ("/poweroff", "#ff6b6b", "Power off"),
        ("/exit", "#b197fc", "Exit"),
    )
    cells = "".join(
        f"<a class='ptile' style='background:{color}' href='{href}'>"
        f"<span>{escape(label)}</span></a>"
        for href, color, label in tiles
    )
    return _page("Parent mode", f"<div class='tiles'>{cells}</div>")


def render_exit() -> str:
    body = "<p>Leaving parent mode...</p><script>window.close();</script>"
    return _page("Parent mode", body)


def render_review(rows: list[ReviewRow]) -> str:
    if not rows:
        return _page("Review games", "<p>No games in the catalog.</p>")
    items = []
    for row in rows:
        rating = f" rating {row.rating}" if row.rating is not None else ""
        items.append(
            f"<li><a href='/review/{escape(row.game_id)}/launch'>{escape(row.name)}</a> "
            f"<span class='badge'>{escape(row.status)}{escape(rating)}</span></li>"
        )
    return _page("Review games", "<ul>" + "".join(items) + "</ul>")


def render_state(name: str, running: bool, outcome: str | None) -> str:
    """Interim trial editor: outcome banner; rename/rating/CTAs come next."""
    refresh = "<meta http-equiv='refresh' content='2'>" if running else ""
    if running:
        body = (
            f"<p>Trial of {escape(name)} is running.</p>"
            "<p>Leave the game with: Volume Down, then Up."
            " This page updates itself.</p>"
        )
    else:
        outcome_text = escape(outcome or "finished")
        body = (
            f"<p>{escape(name)}: trial {outcome_text}.</p>"
            "<p><a href='/review'>Back to the list</a></p>"
        )
    return _page("Trial", refresh + body)


@dataclass(frozen=True)
class WifiView:
    """Everything the Wi-Fi page renders; built by the pages provider."""

    current_ssid: str | None
    connectivity: str
    networks: list[dict[str, str]]
    saved: list[str]
    message: str | None = None


def render_wifi(view: WifiView) -> str:
    body: list[str] = []
    if view.message:
        cls = "err" if "ail" in view.message else "msg"
        body.append(f"<p class='{cls}'>{escape(view.message)}</p>")
    current = view.current_ssid or "not connected"
    body.append(f"<p>Connected to: <b>{escape(current)}</b></p>")
    if view.connectivity == "portal":
        body.append(
            "<div class='portal'>This network needs a sign-in (captive portal). "
            "<a href='/wifi/portal'>Open the sign-in window</a> - close it with "
            "Volume Down, then Up.</div>"
        )
    options = "".join(
        f"<option value=\"{escape(n['ssid'])}\">{escape(n['ssid'])} "
        f"({escape(n['signal'])}% {escape(n['security'])})</option>"
        for n in view.networks
    )
    body.append(
        "<form class='wifi-form' method='post' action='/wifi/connect'>"
        "<label>Network: <select name='ssid'>" + options + "</select></label> "
        "<label>Password: <input type='password' name='password'></label> "
        "<button type='submit'>Connect</button></form>"
    )
    if view.saved:
        saved_items = "".join(
            "<form style='display:inline' method='post' action='/wifi/forget'>"
            f"<input type='hidden' name='name' value=\"{escape(name)}\">"
            f"{escape(name)} <button type='submit'>forget</button></form>"
            for name in view.saved
        )
        body.append("<p>Saved networks: " + saved_items + "</p>")
    body.append("<p><a href='/wifi'>Rescan</a> - <a href='/parent'>Back</a></p>")
    return _page("Wi-Fi", "".join(body))


def render_poweroff() -> str:
    return _page("Power off", "<p>Powering off...</p><script>window.close();</script>")


def render_portal_opened() -> str:
    body = (
        "<p>The sign-in window is open in front of you.</p>"
        "<p>When you are done, close it with <b>Volume Down, then Up</b>.</p>"
    )
    return _page("Sign-in", body)


@dataclass(frozen=True)
class ParentPages:
    """Renderers the server calls per request; each returns full HTML."""

    menu: callable
    review: callable
    wifi: callable
    exit: callable
    poweroff: callable
    review_launch: callable
    review_state: callable
    wifi_connect: callable
    wifi_forget: callable
    wifi_rescan: callable
    wifi_portal: callable


def default_pages() -> ParentPages:
    return ParentPages(
        menu=render_menu,
        review=render_review,
        wifi=render_wifi,
        exit=render_exit,
        poweroff=render_poweroff,
        review_launch=lambda game_id: _page("Starting...", "<p>Starting trial...</p>"),
        review_state=lambda game_id: _page("Trial", "<p>Unknown game.</p>"),
        wifi_connect=lambda ssid, password: render_wifi(
            WifiView(None, "unknown", [], [], "connect is not wired")
        ),
        wifi_forget=lambda name: render_wifi(
            WifiView(None, "unknown", [], [], "forget is not wired")
        ),
        wifi_rescan=lambda: render_wifi(WifiView(None, "unknown", [], [])),
        wifi_portal=lambda: render_portal_opened(),
    )


class _ParentHandler(http.server.BaseHTTPRequestHandler):
    """GET router; routes are matched on the path (no token per owner)."""

    server_version = "LeoParent/1"
    _review_path = re.compile(r"^/review/([0-9a-fA-F-]{36})(/launch)?$")

    def do_GET(self) -> None:  # noqa: N802 - http.server API name
        parsed = urllib.parse.urlparse(self.path)
        pages: ParentPages = self.server.pages
        if parsed.path == "/parent":
            self._send(200, pages.menu())
            return
        if parsed.path == "/review":
            self._send(200, pages.review())
            return
        if parsed.path == "/wifi":
            self._send(200, pages.wifi())
            return
        if parsed.path == "/wifi/rescan":
            self._send(200, pages.wifi_rescan())
            return
        if parsed.path == "/wifi/portal":
            self._send(200, pages.wifi_portal())
            return
        if parsed.path == "/poweroff":
            self._send(200, pages.poweroff())
            return
        if parsed.path == "/exit":
            self._send(200, pages.exit())
            return
        match = self._review_path.match(parsed.path)
        if match is not None:
            try:
                game_id = UUID(match.group(1))
            except ValueError:
                self._send(404, _page("Not found", "<p>Unknown game.</p>"))
                return
            if match.group(2):
                self._send(200, pages.review_launch(game_id))
            else:
                self._send(200, pages.review_state(game_id))
            return
        self._send(404, _page("Not found", "<p>Unknown page.</p>"))

    def do_POST(self) -> None:  # noqa: N802 - http.server API name
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        pages: ParentPages = self.server.pages
        if parsed.path == "/wifi/connect":
            ssid = form.get("ssid", [""])[0].strip()
            password = form.get("password", [""])[0]
            if not ssid:
                self._send(400, _page("Wi-Fi", "<p class='err'>Pick a network.</p>"))
                return
            self._send(200, pages.wifi_connect(ssid, password))
            return
        if parsed.path == "/wifi/forget":
            name = form.get("name", [""])[0].strip()
            if not name:
                self._send(400, _page("Wi-Fi", "<p class='err'>Nothing to forget.</p>"))
                return
            self._send(200, pages.wifi_forget(name))
            return
        self._send(404, _page("Not found", "<p>Unknown page.</p>"))

    def _send(self, code: int, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # keep the launcher log quiet
        return


class ParentServer:
    """Loopback parent UI server; one request-serving thread."""

    def __init__(self, pages: ParentPages, port: int = 0):
        self.pages = pages
        self._httpd = http.server.HTTPServer(("127.0.0.1", port), _ParentHandler)
        self._httpd.pages = pages
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/parent"

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="parent-server"
        )
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None