"""Kiosk UI server: routing, renderers, loopback lifecycle (no token: gesture)."""

import http.client
import json
import re as _re
import urllib.parse
from datetime import date
from uuid import UUID

import pytest

from leo_kiosk.adapters.ui_server import (
    ReviewRow,
    UiPages,
    UiServer,
    WifiView,
    render_blank,
    render_child_state,
    render_editor,
    render_exit,
    render_home,
    render_homechild_pick,
    render_homechild_preview,
    render_menu,
    render_mychild,
    render_portal_opened,
    render_poweroff,
    render_review,
    render_state,
    render_videos,
    render_wifi,
)
from leo_kiosk.domain.reviews import ReviewStatus, StarRating


def default_pages_stub():
    return UiPages(
        home=lambda: "home",
        videos=lambda: "videos",
        child_state=lambda: json.dumps({"status": "", "battery": None}),
        launch_tile=lambda tile_id: f"launch {tile_id}",
        video_play=lambda url: f"play {url}",
        review_save=lambda game_id, form: f"save {game_id}",
        review_delete=lambda game_id: f"delete {game_id}",
        menu=render_menu,
        review=render_review,
        homechild=lambda: "homechild preview",
        homechild_slot=lambda position: f"pick {position}",
        homechild_try=lambda position, game_id: f"try {position} {game_id}",
        homechild_place=lambda position, form: f"place {position} {form}",
        mychild=lambda: "mychild page",
        mychild_save=lambda form: f"mychild save {form}",
        wifi=render_wifi,
        exit=render_exit,
        poweroff=render_poweroff,
        review_launch=lambda game_id, form: f"launch {game_id} {form}",
        review_state=lambda game_id: f"state {game_id}",
        wifi_connect=lambda ssid, password: f"connect {ssid}",
        wifi_forget=lambda name: f"forget {name}",
        wifi_rescan=lambda: "rescan",
        wifi_portal=lambda: "portal",
        thumbnail=lambda name: (b"", 404),
    )


@pytest.mark.local_network
def make_server(pages=None, port=0):
    server = UiServer(pages=pages or default_pages_stub(), port=port)
    server.start()
    return server


def get(path):
    parsed = urllib.parse.urlparse(path)
    conn = http.client.HTTPConnection("127.0.0.1", parsed.port)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    conn.close()
    return response.status, body


def test_menu_page_renders_links():
    html = render_menu()
    assert "<h1>Parent mode</h1>" in html
    assert "href='/review'" in html
    assert "href='/homechild'" in html
    assert "href='/wifi'" in html


def test_review_page_links_launch_and_escapes_names():
    rows = [
        type("R", (), {"game_id": "11111111-1111-1111-1111-111111111111",
                       "name": "<b>Game</b> & Co",
                       "status": ReviewStatus.NEW, "rating": None,
                       "stars": None, "ages": None})(),
        type("R", (), {"game_id": "22222222-2222-2222-2222-222222222222",
                       "name": "Rated one",
                       "status": ReviewStatus.REVIEWED, "rating": 2,
                       "stars": StarRating(3, 2, 4), "ages": None})(),
    ]
    html = render_review(rows)
    assert "&lt;b&gt;Game&lt;/b&gt; &amp; Co" in html
    # new/tested rows launch a trial...
    assert "href='/review/11111111-1111-1111-1111-111111111111/launch'" in html
    # ...reviewed rows open the editor directly (rereading needs no trial)
    assert "href='/review/22222222-2222-2222-2222-222222222222'" in html
    assert "href='/review/22222222-2222-2222-2222-222222222222/launch'" not in html
    assert "new" in html and "reviewed" in html
    assert "★4/2/3" in html  # fun/education/production stars

    selected = [
        ReviewRow("33333333-3333-3333-3333-333333333333", "Sel", "selected", None, "")
    ]
    sel_html = render_review(selected)
    assert "href='/review/33333333-3333-3333-3333-333333333333'" in sel_html
    assert "/launch" not in sel_html


def test_review_page_empty_catalog():
    assert "No games in the catalog." in render_review([])


# --- Home Child: preview grid + per-tile pick list ------------------------
GAME_ID = "11111111-1111-1111-1111-111111111111"


def test_homechild_preview_shows_tiles_and_links_pickers():
    tiles = [
        {"position": 1, "label": "TBD", "color": "#ff6b6b"},
        {"position": 2, "label": "<b>G</b>", "color": "#74c0fc",
         "thumb": f"/thumb/{GAME_ID}.png"},
    ]
    html = render_homechild_preview("LÉO", tiles)
    assert "href='/homechild/1'" in html and "href='/homechild/2'" in html
    assert "TBD" in html and "&lt;b&gt;G&lt;/b&gt;" in html
    assert f"/thumb/{GAME_ID}.png" in html
    # same design as the child home: same stylesheet classes and geometry
    assert "class='grid'" in html and "class='ttitle'>LÉO</div>" in html
    assert "class='gamecell'" in html and "class='cap'" in html
    assert "class='tile'" in html and "class='blank'" in html
    assert "<a class='pback' href='/parent'>Back</a>" in html
    assert "Tile 3" not in html  # exactly the tiles given, padded by caller


def test_homechild_preview_shows_message_banner():
    html = render_homechild_preview(
        "LÉO",
        [{"position": 1, "label": "TBD", "color": "#454551"}],
        message="Tile 3: <b>G</b>",
    )
    assert "Tile 3: &lt;b&gt;G&lt;/b&gt;" in html


def test_homechild_pick_rows_place_into_the_chosen_tile():
    rows = [
        ReviewRow(GAME_ID, "<b>G</b>", "reviewed", "★4/2/3", " ages 4-7"),
        ReviewRow("22222222-2222-2222-2222-222222222222", "Other", "tested", None, ""),
    ]
    html = render_homechild_pick(3, "TBD", rows, message="boom <x>")
    # tile is fixed; rows place into it without asking for a position
    assert "Tile 3: TBD" in html
    assert "action='/homechild/3/place'" in html
    assert f"value='{GAME_ID}'" in html
    assert f"href='/homechild/3/try/{GAME_ID}'" in html
    assert "&lt;b&gt;G&lt;/b&gt;" in html
    # no status words: the list is by definition the tested/reviewed games
    assert "reviewed" not in html and "tested" not in html
    assert "★4/2/3 ages 4-7" in html
    assert "boom &lt;x&gt;" in html
    assert "<a class='back' href='/homechild'>Back</a>" in html
    assert "select name='position'" not in html  # no slot picker, ever
    # empty list keeps the back button
    empty = render_homechild_pick(5, "TBD", [])
    assert "No tested games yet." in empty
    assert "<a class='back' href='/homechild'>Back</a>" in empty


def test_state_page_refreshes_while_running():
    running = render_state("Game", running=True, outcome=None)
    assert "http-equiv='refresh'" in running
    assert "running" in running


def test_editor_asks_for_name_rating_and_age_range():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111",
        "Space Bots",
        StarRating(5, 4, 3),
        4,
        7,
    )
    assert "Trial returned" not in html  # outcome banner removed (owner)
    assert "value='Space Bots'" in html
    assert "data-dim='fun'" in html and "data-dim='education'" in html
    assert "data-dim='production'" in html
    assert "class='star filled'" in html  # prefilled stars paint filled
    assert "name='age_min'" in html and "name='age_max'" in html
    # steppers, not dropdowns; prefilled with the saved range
    assert "<span class='stepval' id='age_min-val'>4</span>" in html
    assert "<span class='stepval' id='age_max-val'>7</span>" in html
    assert "<select" not in html
    assert "data-target='age_min age_max'" in html  # the ✕ clears both
    assert "value='save'" in html and "value='next'" in html
    assert "Delete" in html
    assert "data-confirm='Delete this game?'" in html  # confirmation popup
    assert "href='/review'" in html
    # Try now submits the draft form to the launch endpoint (the draft
    # must survive the trial)
    assert "formaction='/review/11111111-1111-1111-1111-111111111111/launch'" in html
    assert "Try now" in html
    assert "Trial snapshot" not in html  # replaced by the Try now button
    assert "Production<" in html  # label, not "Production value"
    assert "type='range'" not in html  # the 0-100 slider is gone


def test_editor_renders_errors_and_unset_ages():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111", "X", None, None, None,
        error="bad input",
    )
    assert "bad input" in html
    assert "class='star'" in html and "class='star filled'" not in html
    # unset ages display '--' and submit empty values
    assert "<span class='stepval' id='age_min-val'>--</span>" in html
    assert "<input type='hidden' id='age_min' name='age_min' value=''" in html


def test_exit_page_closes_kiosk_window():
    assert "window.close()" in render_exit()


def test_wifi_page_renders_status_form_and_portal_banner():
    view = WifiView(
        current_ssid="Bienvenue Barbidou",
        connectivity="portal",
        networks=[
            {"in_use": True, "ssid": "Bienvenue Barbidou", "signal": "78", "security": "WPA2"},
            {"in_use": False, "ssid": "standup phone", "signal": "55", "security": "WPA2"},
        ],
        saved=["standup phone"],
    )
    html = render_wifi(view)
    assert "Bienvenue Barbidou" in html
    assert "portal" in html and "/wifi/portal" in html
    assert 'value="standup phone"' in html
    assert "action='/wifi/connect'" in html
    assert "action='/wifi/forget'" in html
    assert render_poweroff() != ""
    assert "Volume Down" in render_portal_opened()


def test_home_page_renders_tiles_as_launch_forms():
    tiles = [
        {"id": "read", "label": "ABC", "color": "#ff6b6b", "cmd": ["gcompris-qt"]},
        {"id": "videos", "label": "Videos", "color": "#b197fc", "cmd": ["videos.py"]},
    ]
    html = render_home("LÉO", tiles)
    assert "LÉO" in html
    assert "action='/launch/read'" in html
    assert "href='/videos'" in html  # videos is a routed page, not a launch
    assert "id='rainbow'" in html
    assert "submit" in html  # ACTION_JS: POST responses never replace the page
    for _ in range(6):
        html = render_home("LÉO", [])  # fewer than nine tiles: blanks fill
    assert html.count("class='blank'") == 9


def test_videos_page_renders_nine_tiles_with_play_forms():
    videos = [
        {"title": "Fun|episode", "embed_url": "https://e/1",
         "watch_url": "https://w/1"},
    ]
    html = render_videos(videos)
    assert "action='/videos/play'" in html
    assert "https://w/1" in html
    assert "Fun" in html


def test_child_state_is_json_with_battery():
    payload = json.loads(render_child_state("Ask Papa", (85, True)))
    assert payload["status"] == "Ask Papa"
    assert payload["battery"] == {"percent": 85, "charging": True}
    assert json.loads(render_child_state("", None))["battery"] is None


def test_blank_page_escapes():
    assert "&lt;b&gt;" in render_blank("<b>")


@pytest.mark.local_network
def test_server_serves_menu():
    server = make_server()
    try:
        status, body = get(f"{server.url}")
        assert status == 200
        assert "Parent mode" in body
    finally:
        server.stop()


@pytest.mark.local_network
def test_server_serves_child_routes():
    server = make_server()
    try:
        status, body = get(f"{server.base}/")
        assert status == 200 and body == "home"
        status, body = get(f"{server.base}/videos")
        assert status == 200 and body == "videos"
        status, body = get(f"{server.base}/child-state")
        assert status == 200 and json.loads(body)["status"] == ""
    finally:
        server.stop()


@pytest.mark.local_network
@pytest.mark.local_network
def test_server_routes_thumb_path_with_real_uuid():
    """Regression: the route regex must match a normal '.png' suffix."""
    server = make_server()
    try:
        status, _body = get(
            f"{server.base}/thumb/11111111-1111-1111-1111-111111111111.png"
        )
        assert status in (200, 404)  # stub serves 404; routing itself must resolve
        assert _body == ""  # 404 from the stub, not the unknown-page HTML page
    finally:
        server.stop()


@pytest.mark.local_network
def test_server_routes_review_launch_and_state():
    server = make_server()
    try:
        game = "11111111-1111-1111-1111-111111111111"
        status, body = get(f"http://127.0.0.1:{server.port}/review/{game}/launch")
        assert status == 200 and body == f"launch {game} None"
        status, body = get(f"http://127.0.0.1:{server.port}/review/{game}")
        assert status == 200 and body == f"state {game}"
    finally:
        server.stop()


@pytest.mark.local_network
def test_server_404_on_unknown_route_and_bad_uuid():
    server = make_server()
    try:
        status, _ = get(f"http://127.0.0.1:{server.port}/nope")
        assert status == 404
        status, _ = get(f"http://127.0.0.1:{server.port}/review/not-a-uuid")
        assert status == 404
    finally:
        server.stop()


@pytest.mark.local_network
def test_server_binds_loopback_only():
    server = make_server()
    try:
        assert server._httpd.server_address[0] == "127.0.0.1"
    finally:
        server.stop()

def test_child_and_parent_pages_hide_the_pointer():
    assert "cursor: none" in render_home("LÉO", [])
    assert "cursor: none" in render_menu()


def test_child_state_includes_wifi_availability():
    payload = json.loads(render_child_state("", None, True))
    assert payload["wifi"] == {"available": True}
    assert json.loads(render_child_state("", None))["wifi"] == {"available": False}


@pytest.mark.local_network
def test_review_save_flow_against_a_real_database(tmp_path):
    """Full POST flow: partial stars re-ask, save lands on the next editor.

    Every page call goes through the server thread — the connection is
    thread-confined to whichever thread opens it first.
    """
    import sys

    sys.path.insert(0, ".")
    from leo_kiosk.application import WebUIPages
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = (
            {"provider_id": "pbs", "source_url": "https://a/1",
             "source_name": "One", "media_type": 2},
            {"provider_id": "pbs", "source_url": "https://a/2",
             "source_name": "Two", "media_type": 2},
        )

    import_catalog(db, Source())
    db.close()
    pages = WebUIPages(db_path, {"title": "L", "tiles": []})
    server = UiServer(pages)
    server.start()
    import re as _re

    def get(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode()
        conn.close()
        return response.status, body

    def post(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", path, body=urllib.parse.urlencode(body).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        payload = response.read().decode()
        conn.close()
        return response.status, payload

    try:
        status, list_html = get("/review")
        assert status == 200
        ids = _re.findall(r"/review/([0-9a-f-]{36})/launch", list_html)
        assert len(ids) == 2, list_html

        status, body = post(
            f"/review/{ids[0]}/save",
            {"name": "One", "production": "", "education": "", "fun": "3",
             "age_min": "", "age_max": "", "action": "save"},
        )
        assert status == 200 and "must be integers from 0 to 5" in body

        status, body = post(
            f"/review/{ids[0]}/save",
            {"name": "One", "production": "5", "education": "4", "fun": "3",
             "age_min": "4", "age_max": "7", "action": "next"},
        )
        assert status == 200 and "Review: Two" in body

        status, body = post(
            f"/review/{ids[1]}/save",
            {"name": "Two", "production": "4", "education": "4", "fun": "5",
             "age_min": "", "age_max": "", "action": "save"},
        )
        assert status == 200 and "Review games" in body
        assert "★5/4/4" in body  # fun/education/production
    finally:
        server.stop()

# --- thumbnail tiles and /thumb/ serving ---------------------------------
def test_home_renders_thumbnail_tile_with_caption():
    tiles = [
        {"id": "read", "label": "ABC", "color": "#ff6b6b", "cmd": ["x"],
         "thumb": "/thumb/123e4567-e89b-12d3-a456-426614174000.png"},
        {"id": "maze", "label": "Maze", "color": "#74c0fc", "cmd": ["y"]},
    ]
    html = render_home("LÉO", tiles)
    assert "class='gamecell'" in html
    assert "src='/thumb/123e4567-e89b-12d3-a456-426614174000.png'" in html
    assert "class='cap'>ABC</span>" in html
    assert html.count("class='tile'") == 1  # maze keeps the color tile


def test_home_escapes_thumb_url_and_caption():
    tiles = [
        {"id": "x", "label": "<b>", "color": "#fff", "cmd": ["x"],
         "thumb": '/thumb/x\"><script>alert(1)</script>.png'},
    ]
    html = render_home("L", tiles)
    assert "<script>alert" not in html
    assert "&lt;b&gt;" in html


def test_web_pages_serve_thumbnail_png_and_404_missing(tmp_path):
    """WebUIPages.thumbnail reads the writer's directory; route serves bytes."""
    import uuid

    from leo_kiosk import application

    game_id = uuid.uuid4()
    db_path = tmp_path / "c.sqlite3"
    pages = application.WebUIPages(db_path, {"title": "L", "tiles": []})
    assert pages.thumbnail(f"{game_id}.png") == (b"", 404)  # no row, no file

    from leo_kiosk.services.thumbs import ThumbnailWriter
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS
    from leo_kiosk.storage.thumbs import ThumbnailRepository

    db = open_database(db_path, migrations=MIGRATIONS)
    db.execute(
        "INSERT INTO providers (id, name, website_url) VALUES ('p', 'P', 'https://p.example')"
    )
    db.execute(
        "INSERT INTO games (id, provider_id, canonical_source_url, source_name, media_type) "
        "VALUES (?, 'p', 'https://p.example/g', 'G', 2)",
        (str(game_id),),
    )
    db.commit()
    writer = ThumbnailWriter(ThumbnailRepository(db), tmp_path / "thumbs")
    writer.save(game_id, b"\x89PNG\r\n\x1a\nfake")
    payload, code = pages.thumbnail(f"{game_id}.png")
    assert code == 200 and payload == b"\x89PNG\r\n\x1a\nfake"
    assert pages.thumbnail("not-a-uuid.png") == (b"", 404)
    assert pages.thumbnail(f"{uuid.uuid4()}.png") == (b"", 404)


def test_web_pages_home_attaches_thumb_for_slotted_game(tmp_path):
    """A game placed in a slot with art gets a /thumb/ URL; legacy tiles not."""
    import uuid

    from leo_kiosk import application

    game_id = uuid.uuid4()
    db_path = tmp_path / "c.sqlite3"
    tiles = [
        {"id": "read", "label": "ABC", "color": "#ff6b6b", "cmd": ["x"]},
        {"id": "maze", "label": "Maze", "color": "#74c0fc", "cmd": ["y"]},
    ]
    pages = application.WebUIPages(db_path, {"title": "L", "tiles": tiles})

    from leo_kiosk.services.thumbs import ThumbnailWriter
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.home import HomeRepository
    from leo_kiosk.storage.schema import MIGRATIONS
    from leo_kiosk.storage.thumbs import ThumbnailRepository

    db = open_database(db_path, migrations=MIGRATIONS)
    db.execute(
        "INSERT INTO providers (id, name, website_url) VALUES ('p', 'P', 'https://p.example')"
    )
    db.execute(
        "INSERT INTO games (id, provider_id, canonical_source_url, source_name, media_type) "
        "VALUES (?, 'p', 'https://p.example/g', 'G', 2)",
        (str(game_id),),
    )
    # Slot positions exist only after seeding; seed one legacy tile so
    # position 1 exists, then place the game there.
    seed_tiles = tmp_path / "tiles.json"
    seed_tiles.write_text(
        json.dumps({"title": "L", "columns": 3, "tiles": [{
            "id": "read", "label": "ABC", "color": "#ff6b6b",
            "cmd": ["x"], "minutes": 10}]}),
        encoding="utf-8",
    )
    from leo_kiosk.services.home_seed import seed_home

    seed_home(db, seed_tiles)
    from leo_kiosk.storage.database import transaction

    with transaction(db):
        HomeRepository(db).set_game(1, game_id)  # position 1 replaces tile 1
    db.commit()
    writer = ThumbnailWriter(ThumbnailRepository(db), tmp_path / "thumbs")
    writer.save(game_id, b"\x89PNG\r\n\x1a\nfake")

    html = render_home("L", pages._with_thumbs(tiles))
    assert f"src='/thumb/{game_id}.png'" in html
    assert "class='gamecell'" in html
    # the tile shows the game's name, not the config label (this raw-insert
    # record cannot be decoded, so the name degrades to 'Game')
    assert "class='cap'>Game</span>" in html
    assert ">ABC<" not in html
    # position 2 has no game: color tile with its own label
    assert "action='/launch/maze'" in html
    assert ">Maze<" in html

# --- editor thumbnail display -------------------------------------------
def test_editor_shows_trial_screenshot_when_present():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111",
        "Space Bots",
        None,
        None,
        None,
        thumb="/thumb/11111111-1111-1111-1111-111111111111.png",
    )
    assert "class='ed-shot'" in html
    assert "src='/thumb/11111111-1111-1111-1111-111111111111.png'" in html


def test_editor_shows_fallback_block_without_a_screenshot():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111", "X", None, None, None,
    )
    assert "class='ed-shot-miss'" in html
    assert "No photo yet" in html
    assert "ed-shot'" not in html


def test_editor_escapes_the_thumb_url():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111",
        "X",
        None,
        None,
        None,
        thumb="/thumb/'onerror='alert(1).png",
    )
    # Quotes are entity-escaped inside the single-quoted attribute; the
    # payload cannot break out of src='...'.
    assert "src='/thumb/&#x27;onerror=&#x27;alert(1).png'" in html
    assert "src='/thumb/'" not in html


def test_editor_keeps_form_fields_and_actions():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111",
        "Space Bots",
        StarRating(5, 4, 3),
        4,
        7,
        thumb="/thumb/11111111-1111-1111-1111-111111111111.png",
    )
    assert "name='age_min'" in html and "name='age_max'" in html
    assert "value='save'" in html and "value='next'" in html
    assert "Delete" in html
    assert "href='/review'" in html

def test_editor_bottom_bar_alignment():
    html = render_editor(
        "11111111-1111-1111-1111-111111111111", "X", None, None, None,
    )
    assert "class='ed-foot'" in html
    assert "<a class='back' href='/review'>Back</a>" in html
    # delete and save actions live in the same right-aligned group; CSS makes
    # the nesting irrelevant, so assert the markup order instead.
    assert html.index("ed-actions") < html.index("rbtn-del")
    assert html.index("rbtn-del") < html.index("value='save'")


# --- Home Child: routing and the real-database flow ------------------------
@pytest.mark.local_network
def test_server_routes_homechild_pages_and_place():
    server = make_server()
    try:
        status, body = get(f"{server.base}/homechild")
        assert status == 200 and body == "homechild preview"
        status, body = get(f"{server.base}/homechild/3")
        assert status == 200 and body == "pick 3"
        status, body = get(f"{server.base}/homechild/3/try/{GAME_ID}")
        assert status == 200 and body == f"try 3 {GAME_ID}"
        status, body = post(f"{server.base}/homechild/3/place", {})
        assert status == 200 and body.startswith("place 3")
        status, _ = get(f"{server.base}/homechild/0")
        assert status == 404  # positions are 1-9
        status, _ = get(f"{server.base}/homechild/not-a-position")
        assert status == 404
        status, _ = get(f"{server.base}/homechild/{GAME_ID}")
        assert status == 404  # the old per-game page is gone
    finally:
        server.stop()


def post(path, body):
    parsed = urllib.parse.urlparse(path)
    conn = http.client.HTTPConnection("127.0.0.1", parsed.port)
    payload = urllib.parse.urlencode(body).encode()
    conn.request(
        "POST", path, body=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    conn.close()
    return response.status, data


@pytest.mark.local_network
def test_homechild_flow_against_a_real_database(tmp_path):
    """Review a game, then place it from Home Child: full loop, real SQLite."""
    import sys

    sys.path.insert(0, ".")
    from leo_kiosk.application import WebUIPages
    from leo_kiosk.services.home_seed import seed_home
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.home import HomeRepository
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = (
            {"provider_id": "pbs", "source_url": "https://a/1",
             "source_name": "One", "media_type": 2},
            {"provider_id": "pbs", "source_url": "https://a/2",
             "source_name": "Two", "media_type": 2},
        )

    import_catalog(db, Source())
    tile_config = {
        "title": "L",
        "columns": 3,
        "tiles": [
            {"id": f"tbd{p}", "label": "TBD", "color": "#454551",
             "cmd": ["~/kiosk/tbd"], "minutes": 20}
            for p in range(1, 10)
        ],
    }
    tiles_path = tmp_path / "tiles.json"
    tiles_path.write_text(json.dumps(tile_config))
    assert seed_home(db, tiles_path)
    db.close()
    from leo_kiosk.services.navigation import Route

    pages = WebUIPages(db_path, tile_config)

    class StubController:
        route = Route.HOME_PICKER

        @staticmethod
        def web_trial_state(game_id):
            return False, None

        @staticmethod
        def request_web_trial(game_id, return_to="editor"):
            pass

    pages._controller = StubController()
    server = UiServer(pages)
    server.start()
    import re as _re

    def get2(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode()
        conn.close()
        return response.status, body

    def post2(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", path, body=urllib.parse.urlencode(body).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        payload = response.read().decode()
        conn.close()
        return response.status, payload

    try:
        # the preview shows the child home tiles, not a game list
        status, body = get2(f"{server.base}/homechild")
        assert status == 200 and "TBD" in body
        assert "/homechild/3" in body and "/homechild/9" in body
        assert "<a class='pback' href='/parent'>Back</a>" in body

        # nothing tested yet: tile 3's pick list is empty but has a Back
        status, body = get2(f"{server.base}/homechild/3")
        assert status == 200 and "Tile 3" in body
        assert "No tested games yet." in body
        assert "<a class='back' href='/homechild'>Back</a>" in body

        # review game One through the ordinary editor
        status, list_html = get2(f"{server.base}/review")
        ids = _re.findall(r"/review/([0-9a-f-]{36})/launch", list_html)
        status, body = post2(
            f"/review/{ids[0]}/save",
            {"name": "One", "production": "5", "education": "4", "fun": "3",
             "age_min": "4", "age_max": "7", "action": "save"},
        )
        assert status == 200 and "Review games" in body

        # merely TEST game Two (no stars saved); it must be pickable too
        status, _ = get2(f"{server.base}/review/{ids[1]}/launch")
        assert status == 200

        # tile 3's pick list offers the reviewed and the merely tested game
        status, body = get2(f"{server.base}/homechild/3")
        assert status == 200
        assert "/homechild/3/place" in body
        assert f"value='{ids[0]}'" in body and f"value='{ids[1]}'" in body
        assert f"href='/homechild/3/try/{ids[0]}'" in body
        assert "select name='position'" not in body  # no slot question

        # pick game One for tile 3: placed, back to the preview with a note
        status, body = post2("/homechild/3/place", {"game_id": ids[0]})
        assert status == 200 and "Tile 3: One" in body
        # the preview tile now shows the game
        assert ">One<" in body

        # a merely tested game is pickable too (owner decision 2026-10-26)
        status, body = post2("/homechild/5/place", {"game_id": ids[1]})
        assert status == 200 and "Tile 5: Two" in body

        # persisted: tiles hold the games, selection status is derived
        db2 = open_database(db_path, migrations=MIGRATIONS)
        home = HomeRepository(db2)
        slot3 = home.slot(3)
        assert slot3.game_id is not None and str(slot3.game_id) == ids[0]
        assert slot3.game_id in home.selected_game_ids()
        slot5 = home.slot(5)
        assert slot5.game_id is not None and str(slot5.game_id) == ids[1]
        db2.close()

        # picking for an occupied tile replaces the occupant (explicit tap)
        status, body = post2("/homechild/3/place", {"game_id": ids[1]})
        assert status == 200 and "Tile 3: Two" in body
        db2 = open_database(db_path, migrations=MIGRATIONS)
        home = HomeRepository(db2)
        assert home.slot(3).game_id is not None and str(home.slot(3).game_id) == ids[1]
        assert home.slot_for_game(UUID(ids[0])) is None  # the move cleared it
        db2.close()
    finally:
        server.stop()


# --- on-screen keyboard (always on: the internal AT keyboard node makes
# hardware detection useless on this tablet) -------------------------------
def test_editor_includes_the_osk():
    html = render_editor(GAME_ID, "X", None, None, None)
    assert "leo-osk" in html


def test_wifi_page_includes_the_osk():
    view = WifiView(None, "full", [], [], None)
    assert "leo-osk" in render_wifi(view)


def test_web_pages_always_offer_the_osk(tmp_path):
    import sys

    sys.path.insert(0, ".")
    from leo_kiosk.application import WebUIPages

    pages = WebUIPages(tmp_path / "c.sqlite3", {"title": "L", "tiles": []})
    assert "leo-osk" in pages.wifi()


def test_home_gamecell_caption_is_one_ellipsized_line():
    """Caption spec: space under the thumb, one line, all caps, white."""
    from leo_kiosk.adapters.ui_server import CHILD_CSS

    css = CHILD_CSS.decode()
    block = css.split(".gamecell .cap", 1)[1].split("}", 1)[0]
    assert "font-size: 14px" in block
    assert "letter-spacing: 1px" in block
    assert "text-transform: uppercase" in block
    assert "color: #fff" in css.split(".gamecell .cap", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap" in block
    assert "overflow: hidden" in block
    assert "text-overflow: ellipsis" in block
    # the shot is the screen's aspect ratio; the cell reserves 30px for it
    shot_block = css.split(".gamecell .shot", 1)[1].split("}", 1)[0]
    assert "height: var(--sh)" in shot_block
    cell_block = css.split(".gamecell {", 1)[1].split("}", 1)[0]
    assert "calc(var(--sh) + 30px)" in cell_block


# --- My Child: birthday + age filtering -------------------------------------
def test_mychild_save_button_sits_in_the_footer_with_back():
    html = render_mychild(None, None, [], [])
    assert "id='mychild-form'" in html
    foot = html[html.index("class='ed-foot'"):]
    # Back on the left, Save on the right, one row
    assert "<a class='back' href='/parent'>Back</a>" in foot
    assert "<button type='submit' class='rbtn rbtn-ok' form='mychild-form'>Save</button>" in foot
    assert foot.index("class='back'") < foot.index("rbtn-ok")
    assert "class='mychild'" in html  # footer is fixed to the bottom


def test_mychild_page_asks_for_the_birthday_first():
    html = render_mychild(None, None, [], [])
    assert "No birthday set yet" in html
    assert "name='day'" in html and "name='month'" in html and "name='year'" in html
    assert "action='/mychild'" in html
    assert "<a class='back' href='/parent'>Back</a>" in html
    assert "Right for this age" not in html  # no lists before a birthday exists
    # touch steppers, not dropdowns: big ± buttons around the value
    assert "class='step'" in html and "class='stepval'" in html
    assert "<select" not in html


def test_mychild_page_is_settings_only():
    """No game lists on My Child: the age filter lives in Home Child."""
    html = render_mychild(date(2020, 3, 5), 5)
    assert "Born 2020-03-05" in html and "age 5" in html
    assert "Right for this age" not in html
    assert "No age information" not in html
    assert "<ul class='rlist'>" not in html
    # the steppers are prefilled with the saved birthday
    assert "<span class='stepval' id='day-val'>5</span>" in html
    assert "<span class='stepval' id='month-val'>3</span>" in html
    assert "<span class='stepval' id='year-val'>2020</span>" in html


def test_mychild_page_shows_error_message():
    html = render_mychild(None, None, message="That is not a real date")
    assert "That is not a real date" in html


@pytest.mark.local_network
def test_server_routes_mychild():
    server = make_server()
    try:
        status, body = get(f"{server.base}/mychild")
        assert status == 200 and body == "mychild page"
        status, body = post(f"{server.base}/mychild", {"day": "5"})
        assert status == 200 and body.startswith("mychild save")
    finally:
        server.stop()


@pytest.mark.local_network
def test_mychild_birthday_filters_the_home_child_pick_list(tmp_path):
    """My Child is settings-only; the birthday filters Home Child's lists."""
    import sys

    sys.path.insert(0, ".")
    from datetime import date

    from leo_kiosk.application import WebUIPages
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = (
            {"provider_id": "pbs", "source_url": "https://a/1",
             "source_name": "One", "media_type": 2},
            {"provider_id": "pbs", "source_url": "https://a/2",
             "source_name": "Two", "media_type": 2},
        )

    import_catalog(db, Source())
    db.close()
    pages = WebUIPages(db_path, {"title": "L", "tiles": []})

    from leo_kiosk.services.navigation import Route

    class StubController:
        route = Route.MY_CHILD

    pages._controller = StubController()
    server = UiServer(pages)
    server.start()

    def post2(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", path, body=urllib.parse.urlencode(body).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        payload = response.read().decode()
        conn.close()
        return response.status, payload

    def get2(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode()
        conn.close()
        return response.status, body

    try:
        # settings only: no game lists anywhere on My Child
        status, body = get2(f"{server.base}/mychild")
        assert status == 200 and "Right for this age" not in body
        assert "<ul class='rlist'>" not in body

        # review One with ages 4-7; test Two without any age range
        _, list_html = get2(f"{server.base}/review")
        ids = _re.findall(r"/review/([0-9a-f-]{36})/launch", list_html)
        for game_id, name, age_min, age_max in (
            (ids[0], "One", "4", "7"),
            (ids[1], "Two", "", ""),
        ):
            status, _ = post2(
                f"/review/{game_id}/save",
                {"name": name, "production": "3", "education": "3", "fun": "3",
                 "age_min": age_min, "age_max": age_max, "action": "save"},
            )
            assert status == 200

        # no birthday yet: the pick list shows both tested/reviewed games
        status, body = get2(f"{server.base}/homechild/3")
        assert status == 200 and "One" in body and "Two" in body

        # a 5-year-old: One (4-7) fits; Two (no age range) is out
        today = date.today()
        try:
            birthday = date(today.year - 5, today.month, today.day)
        except ValueError:  # Feb 29
            birthday = date(today.year - 5, 2, 28)
        status, body = post2(
            f"{server.base}/mychild",
            {"day": str(birthday.day), "month": str(birthday.month),
             "year": str(birthday.year), "screen_time": ""},
        )
        assert status == 200 and "age 5" in body

        status, body = get2(f"{server.base}/homechild/3")
        assert status == 200 and "One" in body and "ages 4-7" in body
        assert "Two" not in body
        assert "Nothing suitable for this age yet." not in body

        # a game for 10-14 would be filtered out for the same child
        status, _ = post2(
            f"/review/{ids[1]}/save",
            {"name": "Two", "production": "3", "education": "3", "fun": "3",
             "age_min": "10", "age_max": "14", "action": "save"},
        )
        status, body = get2(f"{server.base}/homechild/3")
        assert "Two" not in body
    finally:
        server.stop()



# --- daily screen time: timer + blocked home --------------------------------
def test_home_shows_timer_and_keeps_tiles_when_time_remains():
    tiles = [{"id": "tbd1", "label": "TBD", "color": "#ff6b6b"}]
    html = render_home("LÉO", tiles, remaining=20)
    assert "<div id='timer'>20 min</div>" in html
    assert "action='/launch/tbd1'" in html  # still tappable
    assert "class='tile off'" not in html


def test_home_blocks_all_tiles_when_time_is_spent():
    tiles = [
        {"id": "tbd1", "label": "TBD", "color": "#ff6b6b"},
        {"id": "videos", "label": "Videos", "color": "#b197fc"},
        {"id": "game", "label": "Game", "color": "#74c0fc",
         "thumb": f"/thumb/{GAME_ID}.png"},
    ]
    html = render_home("LÉO", tiles, remaining=0, blocked=True)
    assert "<div id='timer'>0 min</div>" in html
    assert html.count("class='tile off'") == 2  # legacy + videos tiles
    assert "class='gamecell off'" in html
    assert "action='/launch/" not in html and "href='/videos'" not in html
    assert "grayscale(1)" in html  # the CSS makes the tiles black and white


def test_home_without_a_limit_has_no_timer():
    html = render_home("LÉO", [{"id": "tbd1", "label": "TBD", "color": "#ff6b6b"}])
    assert "id='timer' style='display:none'" in html
    assert "action='/launch/tbd1'" in html


def test_child_state_carries_screen_time():
    import json as _json

    from leo_kiosk.adapters.ui_server import render_child_state as _rcs

    payload = _json.loads(
        _rcs("", None, False, {"remaining": 5, "blocked": False})
    )
    assert payload["screen_time"] == {"remaining": 5, "blocked": False}
    assert _json.loads(_rcs("", None, False))["screen_time"] is None


def test_mychild_page_offers_the_screen_time_setting():
    html = render_mychild(date(2020, 3, 5), 5, screen_time=60)
    assert "<p><b>60 min</b></p>" in html  # just the time, no label prefix
    assert "class='chip selected' data-target='screen_time' data-val='60'" in html
    html = render_mychild(None, None)
    assert "min</b></p>" not in html  # nothing shown when nothing is set
    assert "data-val=''>No limit</button>" in html
    assert "class='chip selected' data-target='screen_time' data-val=''" in html
    html = render_mychild(date(2020, 3, 5), 5, screen_time=0)
    assert "<p><b>0 min</b></p>" in html
    assert "data-val='0'>0 min</button>" in html


@pytest.mark.local_network
def test_screen_time_flow_against_a_real_database(tmp_path):
    """Set a limit, spend the day, and the home locks: real SQLite."""
    import sys

    sys.path.insert(0, ".")
    from datetime import datetime

    from leo_kiosk.application import WebUIPages
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = (
            {"provider_id": "pbs", "source_url": "https://a/1",
             "source_name": "One", "media_type": 2},
        )

    import_catalog(db, Source())
    tiles = {"title": "L", "columns": 3, "tiles": [
        {"id": f"tbd{p}", "label": "TBD", "color": "#454551",
         "cmd": ["~/kiosk/tbd"], "minutes": 20} for p in range(1, 10)]}
    db.close()
    pages = WebUIPages(db_path, tiles)

    from leo_kiosk.services.navigation import Route

    class StubController:
        route = Route.MY_CHILD

    pages._controller = StubController()
    server = UiServer(pages)
    server.start()

    def get2(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode()
        conn.close()
        return response.status, body

    def post2(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", path, body=urllib.parse.urlencode(body).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        payload = response.read().decode()
        conn.close()
        return response.status, payload

    try:
        # no limit yet: timer hidden, tiles active
        status, home_html = get2(f"{server.base}/")
        assert status == 200 and "id='timer' style='display:none'" in home_html
        assert "action='/launch/tbd1'" in home_html

        # set a 60-minute limit through My Child (birthday required first)
        today = datetime.now().date()
        status, body = post2(
            f"{server.base}/mychild",
            {"day": str(today.day), "month": str(today.month),
             "year": str(today.year - 5), "screen_time": "60"},
        )
        assert status == 200 and "<p><b>60 min</b></p>" in body

        # with time remaining the timer shows and tiles stay active
        status, home_html = get2(f"{server.base}/")
        assert "<div id='timer'>60 min</div>" in home_html
        assert "action='/launch/tbd1'" in home_html

        # the parent picks 0: every tile renders grey and inert
        status, body = post2(
            f"{server.base}/mychild",
            {"day": str(today.day), "month": str(today.month),
             "year": str(today.year - 5), "screen_time": "0"},
        )
        assert status == 200 and "<p><b>0 min</b></p>" in body
        status, home_html = get2(f"{server.base}/")
        assert "<div id='timer'>0 min</div>" in home_html
        assert "action='/launch/" not in home_html
        assert "class='tile off'" in home_html

        # a blocked launch is refused server-side too
        status, body = post2(f"{server.base}/launch/tbd1", {})
        assert status == 200 and "No more screen time today!" in body

        # spending the budget blocks the home the same way
        db2 = open_database(db_path, migrations=MIGRATIONS)
        from leo_kiosk.services.child import ScreenTimeService
        from leo_kiosk.storage.child import ChildRepository, ScreenTimeRepository

        usage = ScreenTimeService(ChildRepository(db2), ScreenTimeRepository(db2))
        usage.record(30 * 60, datetime.now())
        usage.set_limit(20)
        db2.close()
        status, home_html = get2(f"{server.base}/")
        assert "<div id='timer'>0 min</div>" in home_html
        assert "action='/launch/" not in home_html

        # an invalid screen-time value is rejected with the page re-asked
        status, body = post2(
            f"{server.base}/mychild",
            {"day": str(today.day), "month": str(today.month),
             "year": str(today.year - 5), "screen_time": "9999"},
        )
        assert status == 200 and "between 0 and 600 minutes" in body
    finally:
        server.stop()


def test_editor_save_buttons_submit_the_draft_form():
    """Regression: the Ok buttons live outside #review-form; without the
    form attribute the POST carried only action=save and every save died
    with 'Name must contain 1-80 characters' (on-device, 2026-10-26)."""
    html = render_editor(
        GAME_ID, "Space Bots", StarRating(5, 4, 3), 4, 7, "return_gesture",
    )
    assert "id='review-form'" in html
    assert "name='name'" in html  # the draft field is in that form
    save = html[html.index("class='ed-actions'"):]
    assert "form='review-form'" in save
    assert "name='action' value='save'" in save
    assert "name='action' value='next'" in save
    # Delete keeps its own form: discarding the draft is the point
    actions_at = html.index("class='ed-actions'")
    save_at = html.index("form='review-form'", actions_at)
    delete = html[html.index("class='ed-delete'"):save_at]
    assert "/delete" in delete
    assert "name='name'" not in delete


@pytest.mark.local_network
def test_delete_lands_on_the_next_game(tmp_path):
    """Regression: deleting used to fall on the previous game (the deleted
    id vanished from the list, index -1 wrapped to the last entry)."""
    import sys

    sys.path.insert(0, ".")
    from leo_kiosk.application import WebUIPages
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = tuple(
            {"provider_id": "pbs", "source_url": f"https://a/{i}",
             "source_name": f"Game {i}", "media_type": 2}
            for i in (1, 2, 3)
        )

    import_catalog(db, Source())
    db.close()
    pages = WebUIPages(db_path, {"title": "L", "tiles": []})

    from leo_kiosk.services.navigation import Route

    class StubController:
        route = Route.REVIEW_EDITOR

        @staticmethod
        def web_trial_state(game_id):
            return False, None

    pages._controller = StubController()
    server = UiServer(pages)
    server.start()

    def post2(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", path, body=urllib.parse.urlencode(body).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        payload = response.read().decode()
        conn.close()
        return response.status, payload

    try:
        _, list_html = get(f"{server.base}/review")
        ids = _re.findall(r"/review/([0-9a-f-]{36})/launch", list_html)
        # review all three so they are all editable (and stay after deletes)
        for game_id in ids:
            status, _ = post2(
                f"/review/{game_id}/save",
                {"name": "N", "production": "3", "education": "3", "fun": "3",
                 "age_min": "", "age_max": "", "action": "save"},
            )
            assert status == 200

        # delete the first: the editor shows the SECOND game
        status, body = post2(f"/review/{ids[0]}/delete", {})
        assert status == 200 and "Review: N" in body  # names are all "N" now
        remaining = _re.findall(r"/review/([0-9a-f-]{36})", body)
        assert ids[1] in remaining and ids[0] not in remaining

        # delete the (now) first again: still lands on the following game
        status, body = post2(f"/review/{ids[1]}/delete", {})
        remaining = _re.findall(r"/review/([0-9a-f-]{36})", body)
        assert ids[2] in remaining and ids[1] not in remaining
    finally:
        server.stop()


def test_editor_uses_the_styled_confirmation_dialog():
    """No window.confirm: the modal is in-page and themed like the UI."""
    html = render_editor(
        GAME_ID, "X", None, None, None,
    )
    assert "data-confirm='Delete this game?'" in html
    assert "window.confirm(" not in html
    assert "hc-modal-overlay" in html and "hc-modal-text" in html
    assert "hc-btn-cancel" in html and "hc-btn-confirm" in html


@pytest.mark.local_network
def test_home_launch_routes_placed_games_to_child_sessions(tmp_path):
    """A placed web game goes to request_child_game; legacy tiles don't."""
    import sys

    sys.path.insert(0, ".")
    from leo_kiosk import application
    from leo_kiosk.application import WebUIPages
    from leo_kiosk.services.home_seed import seed_home
    from leo_kiosk.services.navigation import Route
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.home import HomeRepository
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = (
            {"provider_id": "pbs", "source_url": "https://a/1",
             "source_name": "One", "media_type": 2},
        )

    import_catalog(db, Source())
    game_row = db.execute(
        "SELECT id FROM games WHERE source_name = 'One'"
    ).fetchone()
    from uuid import UUID as _UUID

    game_id = _UUID(game_row[0])
    tiles = {"title": "L", "columns": 3, "tiles": [
        {"id": f"tbd{p}", "label": "TBD", "color": "#454551",
         "cmd": ["~/kiosk/tbd"], "minutes": 20} for p in range(1, 10)]}
    tiles_path = tmp_path / "tiles.json"
    tiles_path.write_text(json.dumps(tiles))
    assert seed_home(db, tiles_path)
    from leo_kiosk.storage.database import transaction

    with transaction(db):
        HomeRepository(db).set_game(2, game_id)
    db.close()

    pages = WebUIPages(db_path, tiles)
    calls = []

    class StubController:
        route = Route.MY_CHILD

        @staticmethod
        def request_child_game(gid, slot, minutes):
            calls.append(("child", gid, slot, minutes))

        @staticmethod
        def launch_tile(tile_id):
            calls.append(("engine", tile_id))

    pages._controller = StubController()
    monkey_idle = application.GLib.idle_add
    application.GLib.idle_add = lambda fn, *a: calls.append(("idle", fn, a))
    server = UiServer(pages)
    server.start()
    try:
        # tile 2 holds the game: child session path with the tile's minutes
        status, _ = post(f"{server.base}/launch/tbd2", {})
        assert status == 200
        kinds = [c for c in calls if c[0] == "idle"]
        fn, args = kinds[-1][1], kinds[-1][2]
        assert fn.__name__ == "request_child_game"
        assert args == (game_id, 2, 20)

        # tile 3 is still a legacy TBD tile: engine path
        calls.clear()
        status, _ = post(f"{server.base}/launch/tbd3", {})
        kinds = [c for c in calls if c[0] == "idle"]
        assert kinds[-1][1].__name__ == "launch_tile"
        assert kinds[-1][2] == ("tbd3",)
    finally:
        application.GLib.idle_add = monkey_idle
        server.stop()


@pytest.mark.local_network
def test_editor_draft_survives_a_try_now(tmp_path):
    """Try now posts the draft; the editor on return shows the same input —
    including a PARTIAL star row that could never be saved before."""
    import sys

    sys.path.insert(0, ".")
    from leo_kiosk.application import WebUIPages
    from leo_kiosk.storage.catalog_import import import_catalog
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "c.sqlite3"
    db = open_database(db_path, migrations=MIGRATIONS)

    class Source:
        checksum = "a" * 64
        providers = (
            {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
        )
        games = (
            {"provider_id": "pbs", "source_url": "https://a/1",
             "source_name": "One", "media_type": 2},
        )

    import_catalog(db, Source())
    db.close()
    pages = WebUIPages(db_path, {"title": "L", "tiles": []})

    from leo_kiosk.services.navigation import Route

    class StubController:
        route = Route.MY_CHILD

        @staticmethod
        def web_trial_state(game_id):
            return False, None

        @staticmethod
        def request_web_trial(game_id):
            pass

    pages._controller = StubController()
    server = UiServer(pages)
    server.start()

    def get2(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode()
        conn.close()
        return response.status, body

    def post2(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", path, body=urllib.parse.urlencode(body).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        payload = response.read().decode()
        conn.close()
        return response.status, payload

    try:
        _, list_html = get2(f"{server.base}/review")
        game_id = _re.findall(r"/review/([0-9a-f-]{36})/launch", list_html)[0]

        # Try now WITH a partial draft (only Fun set; full save would fail)
        status, _ = post2(
            f"/review/{game_id}/launch",
            {"name": "My Name", "production": "", "education": "", "fun": "3",
             "age_min": "4", "age_max": "7"},
        )
        assert status == 200  # trial starts

        # back from the trial: the editor shows the stored draft
        status, body = get2(f"{server.base}/review/{game_id}")
        assert status == 200
        assert "value='My Name'" in body
        assert "class='star filled' data-dim='fun' data-v='3'" in body
        assert "data-dim='production' data-v='1'\"" not in body  # others empty
        assert "<span class='stepval' id='age_min-val'>4</span>" in body

        # completing the rating saves and clears the draft
        status, _ = post2(
            f"/review/{game_id}/save",
            {"name": "My Name", "production": "4", "education": "4", "fun": "3",
             "age_min": "4", "age_max": "7", "action": "save"},
        )
        assert status == 200
        status, body = get2(f"{server.base}/review/{game_id}")
        assert "class='star filled' data-dim='production' data-v='4'" in body
        assert "value='My Name'" in body
        # the draft is gone: this is stored data now, rendered from the DB
        assert pages._drafts.get(UUID(game_id)) is None
    finally:
        server.stop()
