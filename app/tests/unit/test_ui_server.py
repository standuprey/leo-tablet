"""Kiosk UI server: routing, renderers, loopback lifecycle (no token: gesture)."""

import http.client
import json
import urllib.parse

import pytest

from leo_kiosk.adapters.ui_server import (
    UiPages,
    UiServer,
    WifiView,
    render_blank,
    render_child_state,
    render_exit,
    render_home,
    render_menu,
    render_portal_opened,
    render_poweroff,
    render_review,
    render_state,
    render_videos,
    render_wifi,
)
from leo_kiosk.domain.reviews import ReviewStatus


def default_pages_stub():
    return UiPages(
        home=lambda: "home",
        videos=lambda: "videos",
        child_state=lambda: json.dumps({"status": "", "battery": None}),
        launch_tile=lambda tile_id: f"launch {tile_id}",
        video_play=lambda url: f"play {url}",
        corner=lambda: "corner",
        menu=render_menu,
        review=render_review,
        wifi=render_wifi,
        exit=render_exit,
        poweroff=render_poweroff,
        review_launch=lambda game_id: f"launch {game_id}",
        review_state=lambda game_id: f"state {game_id}",
        wifi_connect=lambda ssid, password: f"connect {ssid}",
        wifi_forget=lambda name: f"forget {name}",
        wifi_rescan=lambda: "rescan",
        wifi_portal=lambda: "portal",
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
    assert "href='/wifi'" in html


def test_review_page_links_launch_and_escapes_names():
    rows = [
        type("R", (), {"game_id": "11111111-1111-1111-1111-111111111111",
                       "name": "<b>Game</b> & Co",
                       "status": ReviewStatus.NEW, "rating": None})(),
        type("R", (), {"game_id": "22222222-2222-2222-2222-222222222222",
                       "name": "Rated one",
                       "status": ReviewStatus.REVIEWED, "rating": 2})(),
    ]
    html = render_review(rows)
    assert "&lt;b&gt;Game&lt;/b&gt; &amp; Co" in html
    assert "href='/review/11111111-1111-1111-1111-111111111111/launch'" in html
    assert "new" in html and "reviewed" in html
    assert "rating 2" in html


def test_review_page_empty_catalog():
    assert "No games in the catalog." in render_review([])


def test_state_page_refreshes_while_running_and_shows_outcome_when_done():
    running = render_state("Game", running=True, outcome=None)
    assert "http-equiv='refresh'" in running
    assert "running" in running
    done = render_state("Game", running=False, outcome="PARENT_REQUEST")
    assert "PARENT_REQUEST" in done
    assert "href='/review'" in done


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
    assert "id='corner'" in html
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
def test_server_routes_launch_corner_and_video_play():
    server = make_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", "/launch/read")
        response = conn.getresponse()
        assert response.status == 200 and response.read() == b"launch read"
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        body = urllib.parse.urlencode({"url": "https://w/1"}).encode()
        conn.request("POST", "/videos/play", body=body,
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        assert response.status == 200 and response.read() == b"play https://w/1"
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", server.port)
        conn.request("POST", "/corner")
        response = conn.getresponse()
        assert response.status == 200 and response.read() == b"corner"
        conn.close()
    finally:
        server.stop()


@pytest.mark.local_network
def test_server_routes_review_launch_and_state():
    server = make_server()
    try:
        game = "11111111-1111-1111-1111-111111111111"
        status, body = get(f"http://127.0.0.1:{server.port}/review/{game}/launch")
        assert status == 200 and body == f"launch {game}"
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
