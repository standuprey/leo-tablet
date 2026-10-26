"""Parent server: routing, renderers, loopback lifecycle (no token: gesture)."""

import http.client
import urllib.parse

import pytest

from leo_kiosk.adapters.parent_server import (
    ParentPages,
    ParentServer,
    WifiView,
    render_exit,
    render_menu,
    render_portal_opened,
    render_poweroff,
    render_review,
    render_state,
    render_wifi,
)
from leo_kiosk.domain.reviews import ReviewStatus


def default_pages_stub():
    return ParentPages(
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
    server = ParentServer(pages=pages or default_pages_stub(), port=port)
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