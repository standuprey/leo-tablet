"""Loopback HTTP server for the whole kiosk UI (child and parent).

Single-threaded by design: all requests are served from one dedicated thread,
which owns its own SQLite connection (the storage layer's thread-confinement
contract). The server binds 127.0.0.1 only; the single WebKitGTK view is the
only client. Per the owner, the parent gesture is the only gate for now; no
token is required.

Child pages replicate the legacy GTK screens: the home grid (tiles.json),
the Videos grid (kiosk_videos.json), the touch-reactive rainbow, the battery
gauge and the invisible five-tap parent corner. Actions POST back to this
server; the pages provider marshals them to the GTK main thread.
"""

import http.server
import json
import random
import re
import threading
import urllib.parse
from dataclasses import dataclass
from html import escape
from uuid import UUID

PARENT_CSS = b"""
* { cursor: none; }
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


CHILD_CSS = b"""
* { cursor: none; }
html, body { margin: 0; padding: 0; height: 100%; background: #1b1b2f;
             overflow: hidden; touch-action: manipulation; user-select: none; }
#rainbow { position: fixed; inset: 0; z-index: 0; }
#content { position: relative; z-index: 1; height: 100%; box-sizing: border-box;
           padding: 24px; display: flex; flex-direction: column; }
.ttitle { color: #fff; font-size: 44px; font-weight: 800; text-align: center; }
#status { color: #ffd43b; font-size: 28px; font-weight: 700;
          min-height: 36px; text-align: center; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;
        margin: auto 0; }
.tile { height: 300px; border-radius: 36px; border: none; display: flex;
        align-items: center; justify-content: center; text-decoration: none;
        font-size: 44px; font-weight: 800; color: #1b1b2f; }
.tile span { padding: 0 12px; text-align: center; line-height: 1.15; }
.blank { height: 300px; border-radius: 36px; background: #454551; }
.battery { position: fixed; top: 37px; right: 30px; width: 120px; height: 25px;
           border: 2px solid #fff; border-radius: 3px; z-index: 1; }
.bfill { position: absolute; top: 0; bottom: 0; left: 0; background: #b197fc; }
.bolt { position: absolute; inset: 0; display: flex; align-items: center;
        justify-content: center; color: #ffd43b; font-size: 18px; }
#corner { position: fixed; top: 0; left: 0; width: 110px; height: 110px;
          opacity: 0; z-index: 2; border: none; background: none; padding: 0; }
"""

RAINBOW_JS = b"""
(function(){
  var c=document.getElementById('rainbow'); if(!c) return; var x=c.getContext('2d');
  var PAL=['#ff595e','#ffca3a','#8ac926','#1982c4','#6a4c93','#ff7ab6'];
  var STRIPE=100, SPEED=150, FADE=1.2;
  var scrolling=false, offset=0, anchor=0, startTs=0, fadeStart=null, active=false;
  function size(){c.width=window.innerWidth;c.height=window.innerHeight;}
  window.addEventListener('resize',size); size();
  function secs(){return performance.now()/1000;}
  function draw(alpha){
    x.globalAlpha=1; x.fillStyle='#1b1b2f'; x.fillRect(0,0,c.width,c.height);
    var first=Math.floor(offset/STRIPE), last=Math.floor((offset+c.height)/STRIPE);
    x.globalAlpha=alpha;
    for(var b=first;b<=last;b++){x.fillStyle=PAL[((b%6)+6)%6];
      x.fillRect(0,b*STRIPE-offset,c.width,STRIPE);}
    x.globalAlpha=1;
  }
  function loop(){
    if(scrolling){offset=anchor+(secs()-startTs)*SPEED;draw(1);}
    else if(fadeStart!==null){var a=1-(secs()-fadeStart)/FADE;
      if(a<=0){fadeStart=null;draw(0);active=false;return;}
      draw(a);}
    else{active=false;return;}
    requestAnimationFrame(loop);
  }
  function kick(){if(!active){active=true;requestAnimationFrame(loop);}}
  document.addEventListener('pointerdown',function(){
    scrolling=true;fadeStart=null;anchor=offset;startTs=secs();kick();},true);
  function lift(){if(!scrolling)return;scrolling=false;fadeStart=secs();kick();}
  document.addEventListener('pointerup',lift,true);
  document.addEventListener('pointercancel',lift,true);
})();
"""

ACTION_JS = b"""
(function(){
  // POST responses must never replace the page: submit becomes a fetch.
  document.addEventListener('submit',function(ev){
    var f=ev.target; if(!f||f.tagName!=='FORM') return;
    ev.preventDefault();
    var body=new URLSearchParams(new FormData(f)).toString();
    fetch(f.getAttribute('action')||'.',{method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},body:body})
      .catch(function(){});
  },true);
})();
"""

STATE_JS = b"""
(function(){
  function tick(){
    fetch('/child-state').then(function(r){return r.json();}).then(function(s){
      var st=document.getElementById('status');
      if(st) st.textContent=s.status||'';
      var b=s.battery||{}, g=document.querySelector('.battery');
      if(g){
        if(b.percent===null||b.percent===undefined){g.style.display='none';}
        else{g.style.display='block';
          var f=g.querySelector('.bfill');
          if(f) f.style.width=Math.max(0,Math.min(100,b.percent))+'%';
          var bolt=g.querySelector('.bolt');
          if(bolt) bolt.style.display=b.charging?'flex':'none';}
      }
    }).catch(function(){});
    setTimeout(tick,2000);
  }
  tick();
})();
"""


def _child_page(title: str, body: str, with_battery: bool, with_corner: bool) -> str:
    battery = "<div class='battery'><div class='bfill'></div><div class='bolt'>\u26a1</div></div>" if with_battery else ""
    corner = "<form method='post' action='/corner'><button id='corner' aria-label='parent'></button></form>" if with_corner else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title>"
        f"<style>{CHILD_CSS.decode()}</style></head><body>"
        f"<canvas id='rainbow'></canvas>"
        f"<div id='content'>{battery}{body}</div>{corner}"
        f"<script>{RAINBOW_JS.decode()}{ACTION_JS.decode()}{STATE_JS.decode()}</script></body></html>"
    )


def render_home(title: str, tiles: list[dict[str, object]]) -> str:
    """Child home: the tiles.json grid; the Videos tile navigates, rest launch."""
    cols = 3
    cells = []
    for tile in tiles[:9]:
        label = escape(str(tile.get("label", "")))
        color = escape(str(tile.get("color", "#454551")))
        if str(tile.get("id")) == "videos":
            cells.append(
                f"<a class='tile' style='background:{color}' href='/videos'>"
                f"<span>{label}</span></a>"
            )
        else:
            tile_id = escape(str(tile.get("id", "")))
            cells.append(
                "<form method='post' action='/launch/" + tile_id + "'>"
                f"<button class='tile' style='background:{color}'><span>{label}</span>"
                "</button></form>"
            )
    for _ in range(len(tiles), 9):
        cells.append("<div class='blank'></div>")
    rows = [
        "<div class='grid'>" + "".join(cells[r * cols:(r + 1) * cols]) + "</div>"
        for r in range(3)
    ]
    grid = "".join(rows)
    body = (
        f"<div class='ttitle'>{escape(title)}</div>"
        f"{grid}<div id='status'></div>"
    )
    return _child_page(title, body, with_battery=True, with_corner=True)


def tile_label(video: dict[str, object]) -> str:
    """ASCII-only video title, cut at the first pipe, capped for the tile."""
    title = str(video.get("title") or "").split("|", 1)[0]
    title = "".join(c for c in title if 32 <= ord(c) < 127)
    title = " ".join(title.split())
    if not title:
        return "..."
    return title if len(title) <= 70 else title[:69] + "..."


def load_videos(path: str) -> list[dict[str, object]]:
    """Load the trusted video catalog; reject partial or malformed entries."""
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read video catalog {path}: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"Video catalog {path} must be a nonempty list")
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError(f"Video catalog entry must be an object: {entry!r}")
        title = entry.get("title")
        embed = entry.get("embed_url")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Video entry missing title: {entry!r}")
        if not isinstance(embed, str) or not embed.startswith(("http://", "https://")):
            raise ValueError(f"Video entry missing HTTP(S) embed_url: {entry!r}")
    return data


def render_videos(videos: list[dict[str, object]]) -> str:
    """Videos screen: nine random tiles; playback spawns mpv via videos.py."""
    colors = ("#ff6b6b", "#4dabf7", "#20c997", "#f783ac", "#b197fc",
              "#ffa94d", "#ffd43b", "#82c91e", "#ff8787")
    picked = random.Random().sample(videos, min(9, len(videos)))
    cells = []
    for i, video in enumerate(picked):
        label = escape(tile_label(video))
        url = escape(str(video.get("watch_url") or video["embed_url"]), quote=True)
        cells.append(
            "<form method='post' action='/videos/play'>"
            f"<input type='hidden' name='url' value='{url}'>"
            f"<button class='tile' style='background:{colors[i % len(colors)]}'>"
            f"<span>{label}</span></button></form>"
        )
    for _ in range(len(picked), 9):
        cells.append("<div class='blank'></div>")
    rows = ["<div class='grid'>" + "".join(cells[r * 3:(r + 1) * 3]) + "</div>" for r in range(3)]
    body = "<div class='ttitle'></div>" + "".join(rows) + "<div id='status'></div>"
    return _child_page("VIDEOS", body, with_battery=False, with_corner=False)


def render_child_state(status: str, battery: tuple[int, bool] | None) -> str:
    payload = {
        "status": status,
        "battery": (
            {"percent": battery[0], "charging": battery[1]} if battery else None
        ),
    }
    return json.dumps(payload)


def render_blank(message: str) -> str:
    """Minimal POST response page (the window hides or navigates anyway)."""
    return _page("Leo", f"<p>{escape(message)}</p>")


def render_poweroff() -> str:
    return _page("Power off", "<p>Powering off...</p><script>window.close();</script>")


def render_portal_opened() -> str:
    body = (
        "<p>The sign-in window is open in front of you.</p>"
        "<p>When you are done, close it with <b>Volume Down, then Up</b>.</p>"
    )
    return _page("Sign-in", body)


@dataclass(frozen=True)
class UiPages:
    """Renderers the server calls per request; each returns HTML or JSON."""

    home: callable
    videos: callable
    child_state: callable
    launch_tile: callable
    video_play: callable
    corner: callable
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


def default_pages() -> UiPages:
    return UiPages(
        home=lambda: _page("Leo", "<p>No tiles configured.</p>"),
        videos=lambda: _page("VIDEOS", "<p>No videos configured.</p>"),
        child_state=lambda: render_child_state("", None),
        launch_tile=lambda tile_id: _page("Leo", "<p>Unknown tile.</p>"),
        video_play=lambda url: _page("VIDEOS", "<p>Playback is not wired.</p>"),
        corner=lambda: _page("Leo", "<p>OK</p>"),
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


class _UiHandler(http.server.BaseHTTPRequestHandler):
    """GET/POST router; routes are matched on the path (no token per owner)."""

    server_version = "LeoUI/1"
    _review_path = re.compile(r"^/review/([0-9a-fA-F-]{36})(/launch)?$")
    _launch_path = re.compile(r"^/launch/([a-z0-9-]+)$")

    def do_GET(self) -> None:  # noqa: N802 - http.server API name
        parsed = urllib.parse.urlparse(self.path)
        pages: UiPages = self.server.pages
        if parsed.path == "/":
            self._send(200, pages.home())
            return
        if parsed.path == "/videos":
            self._send(200, pages.videos())
            return
        if parsed.path == "/child-state":
            self._send(200, pages.child_state(), content_type="application/json")
            return
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
        pages: UiPages = self.server.pages
        match = self._launch_path.match(parsed.path)
        if match is not None:
            self._send(200, pages.launch_tile(match.group(1)))
            return
        if parsed.path == "/videos/play":
            self._send(200, pages.video_play(form.get("url", [""])[0]))
            return
        if parsed.path == "/corner":
            self._send(200, pages.corner())
            return
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

    def _send(self, code: int, html: str, content_type: str = "text/html; charset=utf-8") -> None:
        payload = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # keep the launcher log quiet
        return


class UiServer:
    """Loopback kiosk UI server; one request-serving thread."""

    def __init__(self, pages: UiPages, port: int = 0):
        self.pages = pages
        self._httpd = http.server.HTTPServer(("127.0.0.1", port), _UiHandler)
        self._httpd.pages = pages
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def url(self) -> str:
        return f"{self.base}/parent"

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