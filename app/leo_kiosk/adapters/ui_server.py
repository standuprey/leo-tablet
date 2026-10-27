"""Loopback HTTP server for the whole kiosk UI (child and parent).

Single-threaded by design: all requests are served from one dedicated thread,
which owns its own SQLite connection (the storage layer's thread-confinement
contract). The server binds 127.0.0.1 only; the single WebKitGTK view is the
only client. Per the owner, the parent gesture is the only gate for now; no
token is required.

Child pages replicate the legacy GTK screens: the home grid (tiles.json),
the Videos grid (kiosk_videos.json), the touch-reactive rainbow, the battery
gauge. Actions POST back to this server; the pages provider marshals them to
the GTK main thread. The invisible five-tap exit corner is deliberately not
rendered (owner decision: removed from the child interface).
"""

import http.server
import json
import random
import re
import threading
import urllib.parse
from dataclasses import dataclass
from datetime import date
from html import escape
from uuid import UUID

from leo_kiosk.domain.reviews import ReviewStatus, StarRating  # noqa: E402

PARENT_CSS = b"""
* { cursor: none; }
body { background: #0f0f10; color: #ffb000; font-family: sans-serif;
       font-size: 30px; padding: 24px; margin: 0; }
h1 { font-size: 40px; }
a { color: #ffb000; }
/* --- fixed header bar (review pages) ----------------------------------- */
.phead { position: fixed; top: 0; left: 0; right: 0; height: 88px;
         display: flex; align-items: center; justify-content: flex-start;
         padding: 0 24px; background: #0f0f10;
         border-bottom: 2px solid #33323a; box-sizing: border-box; z-index: 10; }
.phead .pback { color: #fff; font-size: 34px; font-weight: 800;
                text-decoration: none; background: rgba(20,20,26,.55);
                padding: 10px 26px; border-radius: 16px; }
.phead .pback:active { background: #4dabf7; color: #1b1b2f; }
.phead .ptitle { color: #fff; font-size: 34px; font-weight: 800;
                 position: absolute; left: 50%; transform: translateX(-50%); }
body.with-header { padding-top: 112px; }
.badge { border: 2px solid #8a8a8a; color: #ddd; padding: 2px 10px;
         border-radius: 4px; font-size: 22px; }
.rlist { margin: 8px 0; padding: 0; list-style: none; }
.rlist li { border-bottom: 2px solid #55524a; }
.rrow { display: flex; align-items: center; justify-content: space-between;
        gap: 16px; padding: 30px 12px; min-height: 96px; box-sizing: border-box;
        text-decoration: none; }
.rrow:active { background: #2c2a22; }
.rname { font-size: 34px; line-height: 1.2; }

/* --- review editor: minimal, calm, generous spacing ------------------- */
.ed { max-width: 820px; margin: 0 auto; display: flex; flex-direction: column;
      gap: 28px; }
.ed-head { display: flex; gap: 28px; align-items: flex-start; }
/* 320 x 213 is the screen's 3:2 aspect: the stored thumbnail (a whole
   screen-aspect capture) displays here uncropped. */
.ed-shot { width: 320px; height: 213px; border-radius: 20px;
           object-fit: cover; display: block; flex: none;
           background: #1a1a1f; }
.ed-shot-miss { width: 320px; height: 213px; border-radius: 20px; flex: none;
                background: #1a1a1f; display: flex; align-items: center;
                justify-content: center; color: #55524a; font-size: 22px;
                letter-spacing: 2px; text-transform: uppercase; }
.ed-title { color: #fff; font-size: 40px; font-weight: 800;
            margin: 4px 0 10px; line-height: 1.15; }
.ed-meta { color: #8a8a8a; font-size: 22px; letter-spacing: 1px;
           text-transform: uppercase; }
.ed .rform { display: flex; flex-direction: column; gap: 22px; margin: 0; }
.ed .rform label { display: flex; flex-direction: column; gap: 10px; margin: 0;
                   font-size: 22px; letter-spacing: 2px; text-transform: uppercase;
                   color: #8a8a8a; }
.ed .rform input[type=text] { font-size: 30px; padding: 16px 18px; width: 100%;
        background: #1a1a1f; color: #eee; border: 2px solid #33323a;
        border-radius: 12px; box-sizing: border-box; }
.ed .rform select { font-size: 26px; padding: 12px; background: #1a1a1f;
        color: #ffb000; border: 2px solid #33323a; border-radius: 10px; }
.ed .rform select option { background: #1a1a1f; }
.ed .starrow { display: flex; align-items: center; gap: 8px; margin: 0; }
.ed .starlabel { font-size: 22px; letter-spacing: 2px; text-transform: uppercase;
                 color: #8a8a8a; width: 240px; }
.ed .star { font-size: 46px; background: none; border: none; padding: 4px 8px;
        color: #55524a; }
.ed .star.filled { color: #ffd43b; }
.ed .star-clear { font-size: 22px; background: none; border: 2px solid #33323a;
        color: #8a8a8a; border-radius: 8px; padding: 2px 10px; }
.ed-actions { display: flex; gap: 16px; align-items: center; }
.ed-actions .rbtn { margin: 0; }
.ed-foot { display: flex; align-items: center; justify-content: space-between;
           margin-top: 12px; }
body.mychild { padding-bottom: 150px; }
.mychild .ed-foot { position: fixed; bottom: 0; left: 0; right: 0;
           margin: 0; padding: 16px 24px; background: #0f0f10;
           border-top: 2px solid #33323a; box-sizing: border-box; z-index: 10; }
.ed-foot .ed-delete { display: contents; }
.ed a.back { color: #8a8a8a; font-size: 22px; letter-spacing: 2px;
             text-transform: uppercase; text-decoration: none; }
.ed a.back:active { color: #ffb000; }
.hc-select { display: flex; align-items: center; gap: 14px; margin: 2px 0 0; }

/* --- My Child: touch steppers and choice chips (no dropdowns) ---------- */
.steps { display: flex; flex-direction: column; gap: 18px; margin: 6px 0 0; }
.steprow { display: flex; align-items: center; gap: 22px; }
.steprow .starlabel { width: 110px; }
.stepblock { display: flex; align-items: center; gap: 12px; }
.step, .stepclear { width: 96px; height: 84px; font-size: 44px; line-height: 1;
        border: none; border-radius: 18px; background: #1f1f27;
        color: #ffb000; }
.stepclear { font-size: 34px; color: #8a8a8a; }
.step:active, .stepclear:active { background: #4dabf7; color: #1b1b2f; }
.stepval { min-width: 150px; text-align: center; font-size: 44px;
           font-weight: 800; color: #fff; }
.ed .steprow .starlabel { width: auto; }
.ed .stepval { font-size: 34px; min-width: 90px; }
.ed .step, .ed .stepclear { width: 76px; height: 68px; font-size: 32px; }
.chips { display: flex; flex-wrap: wrap; gap: 14px; margin: 10px 0 0; }
.chip { height: 76px; padding: 0 30px; font-size: 26px; border: none;
        border-radius: 38px; background: #1f1f27; color: #8a8a8a; }
.chip:active { background: #4dabf7; color: #1b1b2f; }
.chip.selected { background: #8ac926; color: #1b1b2f; font-weight: 800; }
.hc-cell { position: relative; overflow: hidden; }
.hc-cell img { position: absolute; inset: 0; width: 100%; height: 100%;
               object-fit: cover; }
.hc-cell span { position: relative; z-index: 1; background: rgba(20,20,26,.65);
                padding: 4px 16px; border-radius: 10px; }
.pickrow { display: flex; align-items: center; gap: 12px; }
.pickrow form { flex: 1; display: flex; }
.pickrow .rrow { width: 100%; background: none; border: none; color: inherit;
                 font: inherit; text-align: inherit; cursor: inherit;
                 border-bottom: 2px solid #55524a; }
.pickrow .rrow:active { background: #2c2a22; }

/* --- on-screen keyboard: rendered when no hardware keyboard is present - */
.osk { position: fixed; left: 0; right: 0; bottom: 0; z-index: 60;
       display: none; background: #14141a; padding: 10px 8px;
       box-sizing: border-box; }
.osk.on { display: block; }
.osk .krow { display: flex; gap: 6px; margin-bottom: 6px; }
.osk button { flex: 1; height: 64px; font-size: 26px; border: none;
       border-radius: 8px; background: #2b2b35; color: #eee;
       padding: 0; min-width: 0; }
.osk button:active { background: #4dabf7; color: #1b1b2f; }
.osk .kmod { background: #1f1f27; color: #8a8a8a; flex: 0 0 auto;
       min-width: 92px; padding: 0 14px; }
.osk .kmod.on { background: #4dabf7; color: #1b1b2f; }
.osk .kdone { background: #8ac926; color: #1b1b2f; flex: 0 0 auto;
       min-width: 128px; }
.osk .kwide { min-width: 200px; }
.rbtn-try { display: inline-block; background: #ffd43b; color: #1b1b2f;
            text-decoration: none; border-radius: 10px; padding: 10px 24px;
            font-size: 26px; font-weight: 700; }
.rbtn-try:active { background: #e8b90c; }
.editor h1 { display: none; }
.ed-ages { display: flex; align-items: center; gap: 14px; }
.ed-ages .starlabel { width: auto; }
.ed-to { color: #55524a; font-size: 24px; }
.ed .rform select { -webkit-appearance: none; appearance: none;
        width: auto; min-width: 140px; padding-right: 40px;
        background-image: linear-gradient(45deg, transparent 50%, #8a8a8a 50%),
                          linear-gradient(135deg, #8a8a8a 50%, transparent 50%);
        background-position: calc(100% - 24px) 55%, calc(100% - 16px) 55%;
        background-size: 8px 8px; background-repeat: no-repeat; }

.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.ptile { height: 300px; border-radius: 36px; display: flex; align-items: center;
         justify-content: center; font-size: 44px; font-weight: 800;
         color: #1b1b2f; text-decoration: none; }
.portal { background: #ffd43b; color: #1b1b2f; padding: 20px;
          border-radius: 12px; margin: 16px 0; }
.rform label { display: block; margin: 18px 0; font-size: 26px; }
.rform input[type=text] { font-size: 30px; padding: 12px; width: 90%;
        background: #1a1a1f; color: #ffb000; border: 2px solid #8a8a8a; }
.starrow { display: flex; align-items: center; gap: 6px; margin: 10px 0; }
.starlabel { font-size: 26px; width: 220px; }
.star { font-size: 44px; background: none; border: none; padding: 4px 6px;
        color: #55524a; }
.star.filled { color: #ffd43b; }
.star-clear { font-size: 22px; background: none; border: 2px solid #8a8a8a;
        color: #8a8a8a; border-radius: 8px; padding: 2px 8px; margin-left: 8px; }
.rform select { font-size: 26px; padding: 10px; background: #1a1a1f;
        color: #ffb000; border: 2px solid #8a8a8a; }
.rbtn { font-size: 28px; padding: 16px 28px; margin: 10px 12px 10px 0;
        border: none; border-radius: 10px; }
.rbtn-ok { background: #8ac926; color: #1b1b2f; }
.rbtn-next { background: #4dabf7; color: #1b1b2f; }
.rbtn-del { background: #ff6b6b; color: #1b1b2f; }
.err { color: #ff6b6b; font-size: 26px; }

/* --- in-page confirmation dialog (replaces window.confirm) ------------- */
.hc-modal-overlay { position: fixed; inset: 0; background: rgba(10,10,12,.72);
        display: flex; align-items: center; justify-content: center;
        z-index: 100; }
.hc-modal { background: #1a1a1f; border: 2px solid #33323a;
        border-radius: 20px; padding: 30px; max-width: 640px; width: 86%;
        box-sizing: border-box; }
.hc-modal-text { color: #ffb000; font-size: 30px; margin: 0 0 26px;
        line-height: 1.3; }
.hc-modal-actions { display: flex; justify-content: flex-end; gap: 16px; }
.hc-btn-cancel { background: #1f1f27; color: #8a8a8a; border: none;
        border-radius: 10px; padding: 18px 32px; font-size: 26px; }
.hc-btn-cancel:active { background: #4dabf7; color: #1b1b2f; }
.hc-btn-confirm { background: #ff6b6b; color: #1b1b2f; border: none;
        border-radius: 10px; padding: 18px 32px; font-size: 26px;
        font-weight: 800; }
.hc-btn-confirm:active { background: #d94d4d; color: #fff; }
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
    stars: str | None = None
    ages: str | None = None


def _page(
    title: str,
    body: str,
    page_class: str | None = None,
    osk: bool = False,
    header: str | None = None,
) -> str:
    """Parent-mode page shell.

    ``header`` replaces the default <h1> with a fixed header bar (used by
    pages that need a persistent back button); the body gains top padding
    so content clears the bar.
    """
    classes = [page_class] if page_class else []
    if header is not None:
        classes.append("with-header")
    body_tag = f"<body class='{' '.join(classes)}'>" if classes else "<body>"
    osk_script = f"<script>{OSK_JS.decode()}</script>" if osk else ""
    title_html = header if header is not None else f"<h1>{escape(title)}</h1>"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width'>"
        f"<title>{escape(title)}</title>"
        f"<style>{PARENT_CSS.decode()}</style></head>"
        f"{body_tag}{title_html}{body}{osk_script}</body></html>"
    )


def render_menu() -> str:
    tiles = (
        ("/review", "#4dabf7", "Review"),
        ("/homechild", "#74c0fc", "Home Child"),
        ("/mychild", "#ffa94d", "My Child"),
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
    """One row per game: tapping a reviewed/selected game opens its editor
    (the review exists — rereading it needs no trial); new/tested games
    launch a trial, which is the only way to reach their editor."""
    header = _review_header("Review games")
    if not rows:
        return _page("Review games", "<p>No games in the catalog.</p>", header=header)
    items = []
    for row in rows:
        stars = f" {row.stars}" if row.stars else ""
        if row.status in (ReviewStatus.REVIEWED.value, ReviewStatus.SELECTED.value):
            target = f"/review/{escape(row.game_id)}"
        else:
            target = f"/review/{escape(row.game_id)}/launch"
        items.append(
            f"<li><a class='rrow' href='{target}'>"
            f"<span class='rname'>{escape(row.name)}</span>"
            f"<span class='badge'>{escape(row.status)}{escape(stars)}{escape(row.ages or '')}</span></a></li>"
        )
    return _page(
        "Review games", "<ul class='rlist'>" + "".join(items) + "</ul>", header=header
    )


def _review_header(title: str, back_href: str = "/parent") -> str:
    """Fixed header bar for review pages: back button, centered title."""
    return (
        "<header class='phead'>"
        f"<a class='pback' href='{escape(back_href)}'>Back</a>"
        f"<span class='ptitle'>{escape(title)}</span>"
        "</header>"
    )


def render_homechild_preview(
    title: str, tiles: list[dict[str, object]], message: str | None = None
) -> str:
    """Home Child: the child home grid, parent edition.

    The exact design of the child home — same stylesheet, geometry, title,
    thumbs and captions — except every tile links to the pick list for its
    position instead of launching, and a fixed Back link leads to the
    parent menu. Shows exactly what the child sees.
    """
    cells = []
    for tile in tiles[:9]:
        position = int(tile.get("position", 0))
        label = escape(str(tile.get("label", "")))
        color = escape(str(tile.get("color", "#454551")))
        thumb = tile.get("thumb")
        if isinstance(thumb, str) and thumb.startswith("/thumb/"):
            src = escape(thumb, quote=True)
            cells.append(
                f"<a class='gamecell' href='/homechild/{position}'>"
                f"<img class='shot' src='{src}' alt=''>"
                f"<span class='cap'>{label}</span></a>"
            )
        else:
            cells.append(
                f"<a class='tile' style='background:{color}' "
                f"href='/homechild/{position}'><span>{label}</span></a>"
            )
    for _ in range(len(tiles), 9):
        cells.append("<div class='blank'></div>")
    grid = "<div class='grid'>" + "".join(cells) + "</div>"
    note = f"<p class='hcmsg'>{escape(message)}</p>" if message else ""
    body = (
        f"<div class='ttitle'>{escape(title)}</div>"
        + grid
        + note
        + "<a class='pback' href='/parent'>Back</a>"
    )
    return _child_page(title, body, with_battery=True)


def render_homechild_pick(
    position: int,
    occupant: str,
    rows: list[ReviewRow],
    message: str | None = None,
    empty_message: str = "No tested games yet.",
) -> str:
    """Pick a game for one tile: rows place into that tile, no slot picker.

    The tile was chosen on the preview screen, so selecting a game needs no
    position question. Each row also offers a plain try-out.
    """
    err = f"<p class='err'>{escape(message)}</p>" if message else ""
    head = f"<p>Tile {position}: {escape(occupant)}</p>"
    foot = "<div class='ed-foot'><a class='back' href='/homechild'>Back</a></div>"
    if not rows:
        body = f"<div class='ed'>{err}{head}<p>{escape(empty_message)}</p>{foot}</div>"
        return _page(f"Tile {position}", body)
    items = []
    for row in rows:
        # No status badge: everything here is already tested/reviewed; the
        # badge carries only stars and ages.
        badge = f"{row.stars or ''}{row.ages or ''}".strip()
        gid = escape(row.game_id)
        items.append(
            "<li class='pickrow'>"
            "<form method='post' action='/homechild/" + str(position) + "/place'>"
            "<input type='hidden' name='game_id' value='" + gid + "'>"
            "<button class='rrow'><span class='rname'>" + escape(row.name) + "</span>"
            "<span class='badge'>" + escape(badge) + "</span></button></form>"
            "<a class='rbtn rbtn-try' href='/homechild/" + str(position)
            + "/try/" + gid + "'>Try</a>"
            "</li>"
        )
    body = f"<div class='ed'>{err}{head}<ul class='rlist'>{''.join(items)}</ul>{foot}</div>"
    return _page(f"Tile {position}", body)


def _stepper(
    name: str, value: "int | str", minimum: int, maximum: int, label: str = ""
) -> str:
    """Touch-friendly ± stepper: big buttons, a big value, a hidden input.

    The form contract is unchanged (the hidden input carries name/value);
    the buttons only move the number (STEPPER_JS), so saving stays a plain
    form POST with no server changes. An empty value displays '--' and the
    first tap fills the bound (min for '+', max for '-') — used for the
    optional review age range.
    """
    shown = value if value != "" else "--"
    return (
        "<div class='stepblock'>"
        + (f"<span class='starlabel'>{escape(label)}</span>" if label else "")
        + "<button type='button' class='step' data-target='" + name
        + "' data-delta='-1'>−</button>"
        + f"<span class='stepval' id='{name}-val'>{shown}</span>"
        + "<button type='button' class='step' data-target='" + name
        + "' data-delta='1'>+</button>"
        + f"<input type='hidden' id='{name}' name='{name}' value='{value}' "
        + f"data-min='{minimum}' data-max='{maximum}'>"
        + "</div>"
    )


def _stepper_clear(targets: str) -> str:
    """A ✕ button emptying the named steppers (space-separated ids)."""
    return (
        "<button type='button' class='step stepclear' "
        f"data-target='{targets}'>✕</button>"
    )


SCREEN_TIME_CHOICES = (0, 15, 20, 30, 45, 60, 90, 120, 180, 240)


def _chips(label: str, name: str, selected: int | None) -> str:
    """Touch-friendly single-choice chips; '' means 'no limit'."""
    buttons = [f"<button type='button' class='chip{' selected' if selected is None else ''}' "
               f"data-target='{name}' data-val=''>No limit</button>"]
    for value in SCREEN_TIME_CHOICES:
        picked = " selected" if selected == value else ""
        buttons.append(
            f"<button type='button' class='chip{picked}' "
            f"data-target='{name}' data-val='{value}'>{value} min</button>"
        )
    return (
        "<div class='steprow'><span class='starlabel'>"
        + escape(label)
        + "</span></div>"
        + "<div class='chips'>" + "".join(buttons) + "</div>"
        + f"<input type='hidden' id='{name}' name='{name}' "
        + f"value='{'' if selected is None else selected}'>"
    )


STEPPER_JS = b"""
(function(){
  function paint(input){
    document.getElementById(input.id+'-val').textContent =
      input.value==='' ? '--' : input.value;
  }
  document.querySelectorAll('.step').forEach(function(b){
    b.addEventListener('click', function(){
      var input=document.getElementById(b.dataset.target);
      var min=Number(input.dataset.min), max=Number(input.dataset.max);
      var d=Number(b.dataset.delta);
      var v=input.value==='' ? null : Number(input.value);
      if(v===null){ v = d>0 ? min : max; }
      else { v=v+d; if(v<min)v=min; if(v>max)v=max; }
      input.value=v; paint(input);
    });
  });
  document.querySelectorAll('.stepclear').forEach(function(b){
    b.addEventListener('click', function(){
      b.dataset.target.split(' ').forEach(function(id){
        var input=document.getElementById(id);
        if(input){ input.value=''; paint(input); }
      });
    });
  });
  document.querySelectorAll('.chip').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('.chip').forEach(function(c){
        c.classList.remove('selected');
      });
      b.classList.add('selected');
      document.getElementById(b.dataset.target).value=b.dataset.val;
    });
  });
})();
"""


def render_mychild(
    birthday: "date | None",
    age: int | None,
    message: str | None = None,
    screen_time: int | None = None,
) -> str:
    """My Child: birthday and daily screen time, nothing else.

    Touch-friendly steppers and chips (no dropdowns, no keyboard). The
    birthday also drives the age filter on the Home Child pick lists.
    """
    err = f"<p class='err'>{escape(message)}</p>" if message else ""
    head = "<p>No birthday set yet: pick it below.</p>"
    if birthday is not None and age is not None:
        head = f"<p>Born {escape(birthday.isoformat())} — <b>age {age}</b></p>"
    # the setting line shows just the time; nothing at all when unset
    time_head = f"<p><b>{screen_time} min</b></p>" if screen_time is not None else ""
    day = birthday.day if birthday else 1
    month = birthday.month if birthday else 1
    year = birthday.year if birthday else 2020
    parts = (
        "<div class='ed'>"
        + err
        + head
        + time_head
        + "<form id='mychild-form' method='post' action='/mychild'>"
        + "<div class='steps'>"
        + _stepper("day", day, 1, 31, "Day")
        + _stepper("month", month, 1, 12, "Month")
        + _stepper("year", year, 2000, 2030, "Year")
        + "</div>"
        + _chips("Per day", "screen_time", screen_time)
        + "</form>"
    )
    parts += (
        "<div class='ed-foot'>"
        + "<a class='back' href='/parent'>Back</a>"
        + "<button type='submit' class='rbtn rbtn-ok' form='mychild-form'>Save</button>"
        + "</div></div>"
    )
    parts += "<script>" + STEPPER_JS.decode() + "</script>"
    return _page("My Child", parts, page_class="mychild")


def render_state(name: str, running: bool, outcome: str | None) -> str:
    """Running-trial page: banner + self-refresh until the editor appears."""
    refresh = "<meta http-equiv='refresh' content='2'>" if running else ""
    body = (
        f"<p>Trial of {escape(name)} is running.</p>"
        "<p>Leave the game with: Volume Down, then Up."
        " This page updates itself.</p>"
    )
    return _page("Trial", refresh + body)


def _star_row(dimension: str, label: str, value: int | None) -> str:
    stars = []
    for star in range(1, 6):
        filled = " filled" if value is not None and star <= value else ""
        stars.append(
            f"<button type='button' class='star{filled}' data-dim='{dimension}' "
            f"data-v='{star}'>★</button>"
        )
    hidden = "" if value is None else str(value)
    return (
        f"<div class='starrow'><span class='starlabel'>{label}</span>"
        + f"<input type='hidden' name='{dimension}' value='{hidden}'>"
        + "".join(stars)
        + f"<button type='button' class='star-clear' data-dim='{dimension}'>✕</button></div>"
    )


OSK_JS = b"""
(function(){
  // In-page keyboard for text/password inputs; shown only on pages rendered
  // with osk=True (no hardware keyboard detected at render time).
  var kb=document.createElement('div');
  kb.className='osk'; kb.id='leo-osk';
  document.body.appendChild(kb);
  var target=null,shift=false,sym=false;
  var ABC=[
    ['1','2','3','4','5','6','7','8','9','0'],
    ['q','w','e','r','t','y','u','i','o','p'],
    ['a','s','d','f','g','h','j','k','l'],
    ['z','x','c','v','b','n','m']];
  var SYM=[
    ['1','2','3','4','5','6','7','8','9','0'],
    ['@','#','$','_','&','-','+','(',')','/'],
    ['*','"',"'",':',';','!','?','%','='],
    [',','.','-','_']];
  function insert(ch){
    if(!target)return;
    var s=target.selectionStart,e=target.selectionEnd;
    if(s===null||e===null){s=target.value.length;e=s;}
    target.setRangeText(shift?ch.toUpperCase():ch,s,e,'end');
    target.focus();
    if(shift){shift=false;paint();}
  }
  function backspace(){
    if(!target)return;
    var s=target.selectionStart,e=target.selectionEnd;
    if(s===null||e===null)return;
    if(s===e&&s>0){s=s-1;}
    target.setRangeText('',s,e,'end');
    target.focus();
  }
  function key(label,cls,fn){
    var b=document.createElement('button');
    b.textContent=label;
    if(cls)b.className=cls;
    b.addEventListener('pointerdown',function(ev){ev.preventDefault();fn();});
    return b;
  }
  function paint(){
    kb.innerHTML='';
    var rows=sym?SYM:ABC;
    rows.forEach(function(r,i){
      var d=document.createElement('div');d.className='krow';
      if(i===2&&!sym)d.appendChild(key('shift','kmod'+(shift?' on':''),function(){shift=!shift;paint();}));
      r.forEach(function(ch){
        d.appendChild(key(shift?ch.toUpperCase():ch,'',function(){insert(ch);}));
      });
      if(i===2)d.appendChild(key('del','kmod',function(){backspace();}));
      kb.appendChild(d);
    });
    var bottom=document.createElement('div');bottom.className='krow';
    bottom.appendChild(key(sym?'abc':'#+=','kmod',function(){sym=!sym;paint();}));
    bottom.appendChild(key('space','kmod kwide',function(){insert(' ');}));
    bottom.appendChild(key('Done','kdone',function(){hide();}));
    kb.appendChild(bottom);
  }
  function show(){
    paint();kb.classList.add('on');
    if(target&&target.scrollIntoView)target.scrollIntoView({block:'center'});
  }
  function hide(){kb.classList.remove('on');target=null;shift=false;sym=false;}
  document.addEventListener('focusin',function(ev){
    var t=ev.target;
    if(!t||t.tagName!=='INPUT')return;
    if(t.type!=='text'&&t.type!=='password')return;
    target=t;show();
  });
  document.addEventListener('focusout',function(){
    setTimeout(function(){
      if(!kb.classList.contains('on'))return;
      var a=document.activeElement;
      if(!a||a.tagName!=='INPUT'||(a.type!=='text'&&a.type!=='password'))hide();
    },150);
  });
})();
"""


CONFIRM_JS = """
(function(){
  // In-page confirmation styled like the parent UI: window.confirm renders
  // a foreign browser dialog that breaks the kiosk look (and touch flow).
  function showDialog(message, onYes){
    var overlay=document.createElement('div');
    overlay.className='hc-modal-overlay';
    var box=document.createElement('div');
    box.className='hc-modal';
    var text=document.createElement('p');
    text.className='hc-modal-text';
    text.textContent=message;
    var actions=document.createElement('div');
    actions.className='hc-modal-actions';
    var cancel=document.createElement('button');
    cancel.type='button';
    cancel.className='hc-btn-cancel';
    cancel.textContent='Cancel';
    var yes=document.createElement('button');
    yes.type='button';
    yes.className='hc-btn-confirm';
    yes.textContent='Yes, delete';
    actions.appendChild(cancel);
    actions.appendChild(yes);
    box.appendChild(text);
    box.appendChild(actions);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    cancel.addEventListener('click', function(){ overlay.remove(); });
    yes.addEventListener('click', function(){ overlay.remove(); onYes(); });
  }
  document.querySelectorAll("button[data-confirm]").forEach(function(b){
    b.addEventListener("click", function(ev){
      ev.preventDefault();
      showDialog(b.dataset.confirm, function(){
        var form=b.form||b.closest('form');
        if(form){ form.submit(); } else { b.click(); }
      });
    });
  });
})();
"""


STAR_JS = """
(function(){
  function paint(dim, value){
    document.querySelectorAll('.star[data-dim="'+dim+'"]').forEach(function(b){
      b.classList.toggle('filled', Number(b.dataset.v) <= value);
    });
  }
  document.querySelectorAll('.star').forEach(function(b){
    b.addEventListener('click', function(){
      var dim = b.dataset.dim;
      var input = document.querySelector('input[name="'+dim+'"]');
      input.value = b.dataset.v;
      paint(dim, Number(b.dataset.v));
    });
  });
  document.querySelectorAll('.star-clear').forEach(function(b){
    b.addEventListener('click', function(){
      var dim = b.dataset.dim;
      document.querySelector('input[name="'+dim+'"]').value = '';
      paint(dim, -1);
    });
  });
})();
"""


def render_editor(
    game_id: str,
    name: str,
    stars: "StarRating | None",
    age_min: int | None,
    age_max: int | None,
    error: str | None = None,
    thumb: str | None = None,
    osk: bool = True,
    prod: int | None = None,
    edu: int | None = None,
    fun: int | None = None,
) -> str:
    """Post-trial editor: rename, three star rows, age range, parent CTAs.

    Plain form posts (no fetch): each response is the next page the parent
    should see, and full navigation keeps the route tracker honest. The
    draft (name/stars/ages) survives a Try now: the caller passes the
    stored per-dimension values via prod/edu/fun when the parent had set
    only part of the rating — a full StarRating comes through `stars`.
    """
    if stars is not None:
        prod, edu, fun = stars.production, stars.education, stars.fun
    err = f"<p class='err'>{escape(error)}</p>" if error else ""
    shot = (
        f"<img class='ed-shot' src='{escape(thumb, quote=True)}' alt=''>"
        if thumb
        else "<div class='ed-shot-miss'>No photo yet</div>"
    )
    try_now = (
        "<button type='submit' class='rbtn rbtn-try' form='review-form' "
        "formaction='/review/" + escape(game_id) + "/launch'>Try now</button>"
    )
    body = (
        "<div class='ed'>"
        + err
        + "<div class='ed-head'>"
        + shot
        + "<div>"
        + f"<div class='ed-title'>{escape(name)}</div>"
        + try_now
        + "</div></div>"
        + "<form id='review-form' class='rform' method='post' action='/review/"
        + escape(game_id)
        + "/save'>"
        + "<label>Name: <input type='text' name='name' value='"
        + escape(name)
        + "'></label>"
        + "<div class='stars'>"
        + _star_row("fun", "Fun", fun)
        + _star_row("education", "Educational", edu)
        + _star_row("production", "Production", prod)
        + "</div>"
        + "<div class='steprow'>"
        + "<span class='starlabel'>Ages</span>"
        + _stepper("age_min", age_min if age_min is not None else "", 1, 17)
        + "<span class='ed-to'>to</span>"
        + _stepper("age_max", age_max if age_max is not None else "", 1, 17)
        + _stepper_clear("age_min age_max")
        + "</div>"
        + "</form>"
        + "<div class='ed-foot'>"
        + "<a class='back' href='/review'>Back</a>"
        + "<div class='ed-actions'>"
        + "<form class='ed-delete' method='post' action='/review/" + escape(game_id) + "/delete'>"
        + "<button class='rbtn rbtn-del' data-confirm='Delete this game?'>Delete</button></form>"
        # The draft fields (name, stars, ages) live in #review-form; the save
        # buttons must submit THAT form — a nested form here would post only
        # action=save and lose everything the parent typed.
        + "<button class='rbtn rbtn-ok' name='action' value='save' "
        + "form='review-form'>Ok</button>"
        + "<button class='rbtn rbtn-next' name='action' value='next' "
        + "form='review-form'>Ok and see next</button>"
        + "</div>"
        + "</div>"
        + "<script>" + STAR_JS + CONFIRM_JS + STEPPER_JS.decode() + "</script>"
        + "</div>"
    )
    return _page(
        f"Review: {escape(name)}",
        body,
        page_class="editor",
        osk=osk,
        header=_review_header(name, "/review"),
    )


@dataclass(frozen=True)
class WifiView:
    """Everything the Wi-Fi page renders; built by the pages provider."""

    current_ssid: str | None
    connectivity: str
    networks: list[dict[str, str]]
    saved: list[str]
    message: str | None = None


def render_wifi(view: WifiView, osk: bool = True) -> str:
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
    return _page("Wi-Fi", "".join(body), osk=osk)


CHILD_CSS = b"""
* { cursor: none; }
html, body { margin: 0; padding: 0; height: 100%;
             background: linear-gradient(180deg, #1e2c52 0%, #16203c 55%,
                         #101828 100%);
             overflow: hidden; touch-action: manipulation; user-select: none; }
#rainbow { position: fixed; inset: 0; z-index: 0; }
#content { position: relative; z-index: 1; height: 100%; box-sizing: border-box;
           padding: 24px; display: flex; flex-direction: column; }
.ttitle { color: #fff; font-size: 44px; font-weight: 800; text-align: center;
          letter-spacing: -2px; }
#status { color: #ffd43b; font-size: 28px; font-weight: 700;
          min-height: 36px; text-align: center; }
/* Tile geometry: each thumbnail is the screen's aspect ratio (3:2 on this
   device), so a fullscreen capture fits whole and is never cropped. --sh is
   the thumbnail height; the tile is 1.5 * --sh wide and reserves 30px for
   the caption under the art. The bounds keep three rows inside the
   viewport: 296px of fixed chrome (24px page padding x2, ~50px title,
   36px status, 12px grid margins x2, 8px slack) plus 40px of row gaps and
   3 x 30px captions; 88px of horizontal chrome (24px padding x2, 2 x 20px
   gaps). */
:root { --sh: min(calc((100vh - 296px) / 3), calc((100vw - 88px) / 4.5)); }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;
        width: calc(4.5 * var(--sh) + 40px); margin: 12px auto; }
.tile { height: calc(var(--sh) + 30px); border-radius: 36px; border: none;
        display: flex; align-items: center; justify-content: center;
        text-decoration: none; font-size: 44px; font-weight: 800;
        color: #1b1b2f; }
.tile span { padding: 0 12px; text-align: center; line-height: 1.15; }
.blank { height: calc(var(--sh) + 30px); border-radius: 36px;
         background: #454551; }
.gamecell { display: flex; flex-direction: column; align-items: center;
            gap: 8px; background: none; border: none; padding: 0;
            cursor: inherit; height: calc(var(--sh) + 30px); width: 100%;
            box-sizing: border-box; text-decoration: none; }
.gamecell .shot { width: 100%; height: var(--sh); border-radius: 36px;
                  object-fit: cover; display: block; flex: none; }
.gamecell .cap { color: #fff; font-size: 14px; font-weight: 800;
                 text-transform: uppercase; letter-spacing: 1px;
                 text-align: center; padding: 0 8px;
                 /* one line under the thumbnail, ellipsized when too long */
                 height: 22px; line-height: 22px; max-width: 100%;
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.battery { position: fixed; top: 37px; right: 30px; width: 120px; height: 25px;
           border: 2px solid #fff; border-radius: 3px; z-index: 1; }
#timer { position: fixed; top: 37px; left: 30px; color: #fff; font-size: 24px;
         font-weight: 800; z-index: 1; }
.hcmsg { color: #ffd43b; font-size: 26px; font-weight: 700;
         text-align: center; min-height: 36px; }
.pback { position: fixed; top: 24px; left: 24px; color: #fff; font-size: 34px;
         font-weight: 800; text-decoration: none; z-index: 1;
         background: rgba(20,20,26,.55); padding: 14px 30px;
         border-radius: 16px; }
.pback:active { background: #4dabf7; color: #1b1b2f; }
.tile.off, .gamecell.off { filter: grayscale(1); opacity: .55;
                           pointer-events: none; }
.bfill { position: absolute; top: 0; bottom: 0; left: 0; background: #b197fc; }
.bolt { position: absolute; inset: 0; display: flex; align-items: center;
        justify-content: center; color: #ffd43b; font-size: 18px; }
.wifi { position: fixed; top: 37px; right: 158px; width: 26px; height: 25px;
        z-index: 1; display: flex; align-items: center; justify-content: center; }
.wifi svg { width: 24px; height: 22px; }
.wifi .cross { display: none; }
.wifi.off .arcs { stroke: #8a8a8a; fill: #8a8a8a; }
.wifi.off .cross { display: block; }
"""

RAINBOW_JS = b"""
(function(){
  var c=document.getElementById('rainbow'); if(!c) return; var x=c.getContext('2d');
  var PAL=['#ff595e','#ffca3a','#8ac926','#1982c4','#6a4c93','#ff7ab6'];
  var STRIPE=100, SPEED=150, FADE=1.2;
  var scrolling=false, offset=0, anchor=0, startTs=0, fadeStart=null, active=false;
  var bg=null;
  function size(){c.width=window.innerWidth;c.height=window.innerHeight;
    /* matches the body CSS gradient; this canvas paints it opaquely */
    bg=x.createLinearGradient(0,0,0,c.height);
    bg.addColorStop(0,'#1e2c52');bg.addColorStop(.55,'#16203c');bg.addColorStop(1,'#101828');}
  window.addEventListener('resize',size); size();
  function secs(){return performance.now()/1000;}
  function draw(alpha){
    x.globalAlpha=1; x.fillStyle=bg; x.fillRect(0,0,c.width,c.height);
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

WIFI_SVG = """
<svg viewBox='0 0 24 24' fill='none' stroke-width='2.2' stroke-linecap='round'>
  <path class='arcs' d='M3.5 9.5C8.5 4.8 15.5 4.8 20.5 9.5' stroke='#fff'/>
  <path class='arcs' d='M6.5 13C10 9.7 14 9.7 17.5 13' stroke='#fff'/>
  <path class='arcs' d='M9.5 16.4C11 15 13 15 14.5 16.4' stroke='#fff'/>
  <circle class='arcs' cx='12' cy='19.4' r='1.4' fill='#fff' stroke='none'/>
  <path class='cross' d='M3 3L21 21' stroke='#8a8a8a' stroke-width='2.4'/>
</svg>"""

STATE_JS = b"""
(function(){
  function tick(){
    fetch('/child-state').then(function(r){return r.json();}).then(function(s){
      var st=document.getElementById('status');
      if(st) st.textContent=s.status||'';
      var tm=document.getElementById('timer');
      if(tm){var sc=s.screen_time;
        if(sc&&sc.remaining!==null&&sc.remaining!==undefined){
          tm.textContent=sc.remaining+' min'; tm.style.display='block';}
        else{tm.style.display='none';}}
      var b=s.battery||{}, g=document.querySelector('.battery');
      if(g){
        if(b.percent===null||b.percent===undefined){g.style.display='none';}
        else{g.style.display='block';
          var f=g.querySelector('.bfill');
          if(f) f.style.width=Math.max(0,Math.min(100,b.percent))+'%';
          var bolt=g.querySelector('.bolt');
          if(bolt) bolt.style.display=b.charging?'flex':'none';}
      }
      var wf=document.querySelector('.wifi');
      if(wf) wf.classList.toggle('off',(s.wifi||{}).available!==true);
    }).catch(function(){});
    setTimeout(tick,2000);
  }
  tick();
})();
"""


def _child_page(
    title: str, body: str, with_battery: bool, timer: str = ""
) -> str:
    # The invisible five-tap exit corner is deliberately absent: owner
    # decision — removed from the child interface (architecture.md).
    battery = (
        "<div class='wifi off'>" + WIFI_SVG + "</div>"
        "<div class='battery'><div class='bfill'></div><div class='bolt'>\u26a1</div></div>"
        if with_battery
        else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title>"
        f"<style>{CHILD_CSS.decode()}</style></head><body>"
        f"<canvas id='rainbow'></canvas>"
        f"<div id='content'>{timer}{battery}{body}</div>"
        f"<script>{RAINBOW_JS.decode()}{ACTION_JS.decode()}{STATE_JS.decode()}</script></body></html>"
    )


def render_home(
    title: str,
    tiles: list[dict[str, object]],
    remaining: int | None = None,
    blocked: bool = False,
) -> str:
    """Child home: the tiles.json grid; the Videos tile navigates, rest launch.

    A tile with a thumb URL renders as game art with a caption instead of
    the flat color block; missing/failed art falls back to color+label.
    When the daily screen-time budget is spent (blocked=True), every tile
    renders grey and inert; a timer shows what is left of today.
    """
    cells = []
    for tile in tiles[:9]:
        label = escape(str(tile.get("label", "")))
        color = escape(str(tile.get("color", "#454551")))
        thumb = tile.get("thumb")
        if str(tile.get("id")) == "videos":
            if blocked:
                cells.append(
                    f"<span class='tile off' style='background:{color}'>"
                    f"<span>{label}</span></span>"
                )
            else:
                cells.append(
                    f"<a class='tile' style='background:{color}' href='/videos'>"
                    f"<span>{label}</span></a>"
                )
        elif isinstance(thumb, str) and thumb.startswith("/thumb/"):
            tile_id = escape(str(tile.get("id", "")))
            src = escape(thumb, quote=True)
            if blocked:
                cells.append(
                    "<span class='gamecell off'>"
                    f"<img class='shot' src='{src}' alt=''>"
                    f"<span class='cap'>{label}</span></span>"
                )
            else:
                cells.append(
                    "<form method='post' action='/launch/" + tile_id + "'>"
                    "<button class='gamecell'>"
                    f"<img class='shot' src='{src}' alt=''>"
                    f"<span class='cap'>{label}</span>"
                    "</button></form>"
                )
        else:
            tile_id = escape(str(tile.get("id", "")))
            if blocked:
                cells.append(
                    f"<span class='tile off' style='background:{color}'>"
                    f"<span>{label}</span></span>"
                )
            else:
                cells.append(
                    "<form method='post' action='/launch/" + tile_id + "'>"
                    f"<button class='tile' style='background:{color}'><span>{label}</span>"
                    "</button></form>"
                )
    for _ in range(len(tiles), 9):
        cells.append("<div class='blank'></div>")
    grid = "<div class='grid'>" + "".join(cells) + "</div>"
    if remaining is not None:
        timer = f"<div id='timer'>{remaining} min</div>"
    else:
        timer = "<div id='timer' style='display:none'></div>"
    body = (
        f"<div class='ttitle'>{escape(title)}</div>"
        f"{grid}<div id='status'></div>"
    )
    return _child_page(title, body, with_battery=True, timer=timer)


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
    grid = "<div class='grid'>" + "".join(cells) + "</div>"
    body = "<div class='ttitle'></div>" + grid + "<div id='status'></div>"
    return _child_page("VIDEOS", body, with_battery=False)


def render_child_state(
    status: str,
    battery: tuple[int, bool] | None,
    wifi_available: bool = False,
    screen_time: dict[str, object] | None = None,
) -> str:
    payload = {
        "status": status,
        "battery": (
            {"percent": battery[0], "charging": battery[1]} if battery else None
        ),
        "wifi": {"available": wifi_available},
        "screen_time": screen_time,
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
    review_save: callable
    review_delete: callable
    menu: callable
    review: callable
    homechild: callable
    homechild_slot: callable
    homechild_try: callable
    homechild_place: callable
    mychild: callable
    mychild_save: callable
    wifi: callable
    exit: callable
    poweroff: callable
    review_launch: callable
    review_state: callable
    wifi_connect: callable
    wifi_forget: callable
    wifi_rescan: callable
    wifi_portal: callable
    thumbnail: callable


def default_pages() -> UiPages:
    return UiPages(
        home=lambda: _page("Leo", "<p>No tiles configured.</p>"),
        videos=lambda: _page("VIDEOS", "<p>No videos configured.</p>"),
        child_state=lambda: render_child_state("", None),
        launch_tile=lambda tile_id: _page("Leo", "<p>Unknown tile.</p>"),
        video_play=lambda url: _page("VIDEOS", "<p>Playback is not wired.</p>"),
        review_save=lambda game_id, form: _page("Review", "<p>Save is not wired.</p>"),
        review_delete=lambda game_id: _page("Review", "<p>Delete is not wired.</p>"),
        menu=render_menu,
        review=render_review,
        homechild=lambda: _page("Home Child", "<p>Not wired.</p>"),
        homechild_slot=lambda position: _page("Home Child", "<p>Not wired.</p>"),
        homechild_try=lambda position, game_id: _page("Starting...", "<p>Not wired.</p>"),
        homechild_place=lambda position, form: _page("Home Child", "<p>Not wired.</p>"),
        mychild=lambda: _page("My Child", "<p>Not wired.</p>"),
        mychild_save=lambda form: _page("My Child", "<p>Not wired.</p>"),
        wifi=render_wifi,
        exit=render_exit,
        poweroff=render_poweroff,
        review_launch=lambda game_id, form: _page("Starting...", "<p>Starting trial...</p>"),
        review_state=lambda game_id: _page("Trial", "<p>Unknown game.</p>"),
        wifi_connect=lambda ssid, password: render_wifi(
            WifiView(None, "unknown", [], [], "connect is not wired")
        ),
        wifi_forget=lambda name: render_wifi(
            WifiView(None, "unknown", [], [], "forget is not wired")
        ),
        wifi_rescan=lambda: render_wifi(WifiView(None, "unknown", [], [])),
        wifi_portal=lambda: render_portal_opened(),
        thumbnail=lambda name: (b"", 404),
    )


class _UiHandler(http.server.BaseHTTPRequestHandler):
    """GET/POST router; routes are matched on the path (no token per owner)."""

    server_version = "LeoUI/1"
    _review_path = re.compile(r"^/review/([0-9a-fA-F-]{36})(/launch)?$")
    _review_write_path = re.compile(r"^/review/([0-9a-fA-F-]{36})/(save|delete|launch)$")
    _homechild_path = re.compile(
        r"^/homechild/([1-9])(/try/([0-9a-fA-F-]{36}))?$"
    )
    _homechild_place_path = re.compile(r"^/homechild/([1-9])/place$")
    _launch_path = re.compile(r"^/launch/([a-z0-9-]+)$")
    _thumb_path = re.compile(r"^/thumb/([0-9a-fA-F-]{36}\.png)$")

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
        thumb_match = self._thumb_path.match(parsed.path)
        if thumb_match is not None:
            payload, code = pages.thumbnail(thumb_match.group(1))
            self._send(
                code,
                payload,
                content_type="image/png" if code == 200 else "text/plain",
            )
            return
        if parsed.path == "/parent":
            self._send(200, pages.menu())
            return
        if parsed.path == "/review":
            self._send(200, pages.review())
            return
        if parsed.path == "/homechild":
            self._send(200, pages.homechild())
            return
        if parsed.path == "/mychild":
            self._send(200, pages.mychild())
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
                self._send(200, pages.review_launch(game_id, None))
            else:
                self._send(200, pages.review_state(game_id))
            return
        match = self._homechild_path.match(parsed.path)
        if match is not None:
            position = int(match.group(1))
            if match.group(2):
                try:
                    game_id = UUID(match.group(3))
                except ValueError:
                    self._send(404, _page("Not found", "<p>Unknown game.</p>"))
                    return
                self._send(200, pages.homechild_try(position, game_id))
            else:
                self._send(200, pages.homechild_slot(position))
            return
        self._send(404, _page("Not found", "<p>Unknown page.</p>"))

    def do_POST(self) -> None:  # noqa: N802 - http.server API name
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        pages: UiPages = self.server.pages
        write_match = self._review_write_path.match(parsed.path)
        if write_match is not None:
            game_id = UUID(write_match.group(1))
            kind = write_match.group(2)
            if kind == "save":
                self._send(200, pages.review_save(game_id, form))
            elif kind == "launch":
                self._send(200, pages.review_launch(game_id, form))
            else:
                self._send(200, pages.review_delete(game_id))
            return
        homechild_match = self._homechild_place_path.match(parsed.path)
        if homechild_match is not None:
            self._send(200, pages.homechild_place(int(homechild_match.group(1)), form))
            return
        match = self._launch_path.match(parsed.path)
        if match is not None:
            self._send(200, pages.launch_tile(match.group(1)))
            return
        if parsed.path == "/videos/play":
            self._send(200, pages.video_play(form.get("url", [""])[0]))
            return
        if parsed.path == "/mychild":
            self._send(200, pages.mychild_save(form))
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

    def _send(self, code: int, body: str | bytes, content_type: str = "text/html; charset=utf-8") -> None:
        payload = body if isinstance(body, bytes) else body.encode("utf-8")
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