"""Controller wiring: routes map to loopback pages; web actions drive the engine.

Replaces the removed display-marked wiring tests; everything here runs
headless against a fake window host.
"""

import json
from uuid import uuid4

import pytest

from leo_kiosk import application
from leo_kiosk.domain.gestures import (
    DEFAULT_PATTERNS,
    PARENT_SURFACE_PATTERNS,
    GestureAction,
)
from leo_kiosk.services.navigation import Route


class FakeWindow:
    def __init__(self):
        self.navigations = []
        self.shown = 0
        self.hidden = 0
        self.visible = True
        self.on_webview_close = None
        self.snapshots = []
        self.toasts = []
        self.zooms = []

    def navigate(self, url):
        self.navigations.append(url)

    def hide(self):
        self.hidden += 1
        self.visible = False

    def show(self):
        self.shown += 1
        self.visible = True

    def is_showing(self):
        return self.visible

    def show_loader(self, text="Starting..."):
        self.loader = text

    def hide_loader(self):
        self.loader = None

    def capture_snapshot(self, on_done):
        self.snapshots.append(on_done)

    def toast(self, message):
        self.toasts.append(message)

    def page_size(self):
        return (1280, 1920)

    def set_page_zoom(self, factor):
        self.zooms.append(factor)


class FakeServer:
    base = "http://127.0.0.1:1"


class FakeRecognizer:
    def __init__(self):
        self.patterns = []

    def use_patterns(self, patterns):
        self.patterns.append(patterns)


class FakeMonitor:
    def __init__(self):
        self.recognizer = FakeRecognizer()


class RecordingPopen:
    def __init__(self, pid=70001, fail=False):
        self.pid = pid
        self.fail = fail
        self.calls = []
        self.start_new_session = None
        self.returncode = None

    def __call__(self, cmd, start_new_session=False, stdout=None, stderr=None):
        self.calls.append(tuple(cmd))
        self.start_new_session = start_new_session
        if self.fail:
            raise OSError("executable missing")
        return self

    def poll(self):
        return self.returncode


CONFIG = {
    "title": "LÉO",
    "tiles": [
        {"id": "read", "label": "ABC", "color": "#ff6b6b",
         "cmd": ["gcompris-qt"], "minutes": 25},
        {"id": "videos", "label": "Videos", "color": "#b197fc",
         "cmd": ["~/kiosk/videos.py"], "minutes": 20},
    ],
}


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setattr(application, "STATE", str(tmp_path / ".app-pid"))
    monkeypatch.setattr(application, "VOICES", str(tmp_path / "voices"))
    popen = RecordingPopen()
    monkeypatch.setattr(application, "_popen", popen)
    monkeypatch.setattr(application, "play", lambda path: None)
    window = FakeWindow()
    controller = application.AppController(window, CONFIG, server=FakeServer())
    controller.launcher._test_popen = popen
    return controller, window, tmp_path


def test_enter_parent_from_child_home_navigates_to_parent(controller):
    controller, window, _tmp = controller
    controller.on_gesture(GestureAction.ENTER_PARENT)
    assert controller.route is Route.PARENT_HOME
    assert window.navigations == ["http://127.0.0.1:1/parent"]


def test_return_from_parent_home_returns_to_child_home(controller):
    controller, window, _tmp = controller
    controller.on_gesture(GestureAction.ENTER_PARENT)
    controller.on_gesture(GestureAction.RETURN)
    assert controller.route is Route.CHILD_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/"


def test_gestures_are_ignored_while_an_app_is_foregrounded(controller):
    controller, window, _tmp = controller
    window.visible = False
    controller.on_gesture(GestureAction.ENTER_PARENT)
    assert controller.route is Route.CHILD_HOME


def test_videos_tile_navigates_to_the_videos_page(controller):
    controller, window, _tmp = controller
    controller.launch_tile("videos")
    assert controller.route is Route.VIDEOS
    assert window.navigations == ["http://127.0.0.1:1/videos"]


def test_play_video_runs_through_the_videos_script_and_returns_to_videos(
    controller, monkeypatch
):
    controller, window, tmp_path = controller
    controller.route = Route.VIDEOS
    monkeypatch.setattr(application, "VIDEOS_SCRIPT", str(tmp_path / "videos.py"))
    (tmp_path / "videos.py").write_text("#!/usr/bin/env python3\n")
    controller.play_video("https://www.youtube.com/watch?v=x")
    assert controller.route is Route.CHILD_ACTIVITY
    assert (tmp_path / ".app-pid").read_text() == "70001"
    controller.launcher.proc.returncode = 0
    controller.launcher._watch()
    assert window.navigations == ["http://127.0.0.1:1/videos"]
    assert not (tmp_path / ".app-pid").exists()


def test_play_video_rejects_non_http_urls(controller, monkeypatch):
    controller, window, tmp_path = controller
    controller.route = Route.VIDEOS
    monkeypatch.setattr(application, "VIDEOS_SCRIPT", str(tmp_path / "videos.py"))
    controller.play_video("file:///etc/passwd")
    assert controller.route is Route.VIDEOS
    assert controller.status_text() == "Cannot play this one!"
    assert window.hidden == 0


def test_native_tile_launches_the_engine_and_hides_the_window(controller):
    controller, window, tmp_path = controller
    controller.launch_tile("read")
    assert controller.route is Route.CHILD_ACTIVITY
    assert window.hidden == 1
    assert controller.launcher._test_popen.calls == [("gcompris-qt",)]
    assert (tmp_path / ".app-pid").read_text() == "70001"


def test_native_tile_launch_from_parent_route_is_ignored(controller):
    controller, window, tmp_path = controller
    controller.route = Route.PARENT_HOME
    controller.launch_tile("read")
    assert window.hidden == 0
    assert not (tmp_path / ".app-pid").exists()


def test_app_exit_returns_to_child_home(controller):
    controller, window, tmp_path = controller
    controller.launch_tile("read")
    controller.launcher.proc.returncode = 0
    controller.launcher._watch()
    assert controller.route is Route.CHILD_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/"
    assert window.shown == 1
    assert not (tmp_path / ".app-pid").exists()


def test_web_navigated_follows_page_links(controller):
    controller, _window, _tmp = controller
    monitor = FakeMonitor()
    controller.monitor = monitor
    controller.web_navigated("http://127.0.0.1:1/parent")
    assert controller.route is Route.PARENT_HOME
    assert monitor.recognizer.patterns[-1] == PARENT_SURFACE_PATTERNS
    controller.web_navigated("http://127.0.0.1:1/videos")
    assert controller.route is Route.VIDEOS
    controller.web_navigated("http://127.0.0.1:1/")
    assert controller.route is Route.CHILD_HOME
    assert monitor.recognizer.patterns[-1] == DEFAULT_PATTERNS


def test_web_navigated_ignores_unknown_paths_and_hidden_window(controller):
    controller, window, _tmp = controller
    controller.web_navigated("http://127.0.0.1:1/nope")
    assert controller.route is Route.CHILD_HOME
    window.visible = False
    controller.web_navigated("http://127.0.0.1:1/parent")
    assert controller.route is Route.CHILD_HOME  # hidden: trial/app owns exits


def test_down_up_from_any_shown_surface_goes_child_home(controller):
    controller, window, _tmp = controller
    controller.web_navigated("http://127.0.0.1:1/review")
    controller.on_gesture(GestureAction.RETURN)
    assert controller.route is Route.CHILD_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/"


def test_webview_close_returns_to_child_home(controller):
    controller, window, _tmp = controller
    controller.route = Route.PARENT_HOME
    controller.webview_closed()
    assert controller.route is Route.CHILD_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/"



def test_trial_finish_shows_the_interim_state_page(controller):
    controller, window, _tmp = controller
    game = uuid4()
    controller.trial_finished(game, "return_gesture")
    assert controller.route is Route.PARENT_HOME
    assert window.navigations == [f"http://127.0.0.1:1/review/{game}"]
    # in-view trials: the window was never hidden, so nothing to re-show
    assert window.shown == 0


def test_pattern_set_follows_the_surface(controller):
    controller, _window, _tmp = controller
    monitor = FakeMonitor()
    controller.monitor = monitor
    controller.on_gesture(GestureAction.ENTER_PARENT)  # parent surface
    assert monitor.recognizer.patterns[-1] == PARENT_SURFACE_PATTERNS
    controller.on_gesture(GestureAction.RETURN)  # back to child home
    assert monitor.recognizer.patterns[-1] == DEFAULT_PATTERNS


def test_app_exit_returns_to_the_child_home(controller):
    controller, window, _tmp = controller
    controller.launch_tile("read")
    controller.launcher.proc.returncode = 0
    controller.launcher._watch()
    assert controller.route is Route.CHILD_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/"


def test_status_message_expires(controller, monkeypatch):
    controller, _window, _tmp = controller
    value = {"now": 100.0}
    monkeypatch.setattr(application.time, "monotonic", lambda: value["now"])
    controller.say("Ask Papa to fix this one!")
    assert controller.status_text() == "Ask Papa to fix this one!"
    value["now"] += 4.0
    assert controller.status_text() == ""


def test_config_helper_reads_tiles(tmp_path):
    config = tmp_path / "tiles.json"
    config.write_text(json.dumps({"title": "LÉO", "tiles": CONFIG["tiles"]}),
                      encoding="utf-8")
    loaded = application._load_config(str(config))
    assert loaded["title"] == "LÉO"
    assert len(loaded["tiles"]) == 2


def test_config_helper_degrades_on_unreadable_file(tmp_path):
    assert application._load_config(str(tmp_path / "missing.json")) == {}


def test_videos_page_degrades_when_the_catalog_is_missing(controller, monkeypatch):
    from leo_kiosk.application import WebUIPages

    monkeypatch.setattr(application, "KIOSK_VIDEOS", "/nonexistent/videos.json")
    pages = WebUIPages("/nonexistent.db", CONFIG)
    html = pages.videos()
    assert "No videos" in html


def test_return_gesture_leaves_the_portal_and_returns_to_wifi(controller):
    controller, window, _tmp = controller
    controller.web_navigated("http://127.0.0.1:1/wifi")
    controller.portal_active = True
    controller.on_gesture(GestureAction.RETURN)
    assert controller.portal_active is False
    assert controller.route is Route.WIFI
    assert window.navigations[-1] == "http://127.0.0.1:1/wifi"


def test_enter_parent_leaves_the_portal_and_goes_parent_home(controller):
    controller, window, _tmp = controller
    controller.web_navigated("http://127.0.0.1:1/wifi")
    controller.portal_active = True
    controller.on_gesture(GestureAction.ENTER_PARENT)
    assert controller.portal_active is False
    assert controller.route is Route.PARENT_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/parent"


def test_trial_runs_in_the_view_without_hiding_the_window(controller, monkeypatch):
    from leo_kiosk.domain.errors import ValidationError

    controller, window, _tmp = controller

    class Catalog:
        @staticmethod
        def get_entry(game_id):
            class Entry:
                playable_url = "https://games.example/play"
                display_name = "Game A"
            return Entry()

    class Sessions:
        @staticmethod
        def start_trial(url, game_id):
            return game_id

        @staticmethod
        def stop(token, outcome):
            pass

    controller.catalog = Catalog()
    controller.sessions = Sessions()
    controller.request_web_trial(game := uuid4())
    assert controller.route is Route.REVIEW_TRIAL
    assert window.hidden == 0
    assert window.navigations[-1] == "https://games.example/play"
    controller.trial_finished(game, "return_gesture")
    assert window.navigations[-1] == f"http://127.0.0.1:1/review/{game}"

    # service failure: stay put, no crash
    class Failing:
        @staticmethod
        def get_entry(game_id):
            class Entry:
                playable_url = "https://games.example/play"
            return Entry()

    class Refusing:
        @staticmethod
        def start_trial(url, game_id):
            raise ValidationError("A trial is already running")

    controller.catalog = Failing()
    controller.sessions = Refusing()
    controller.request_web_trial(game)
    assert window.hidden == 0


def test_wifi_icon_state_from_adapter_with_caching(controller, monkeypatch):
    import time as time_module

    from leo_kiosk.adapters import wifi as wifi_adapter
    from leo_kiosk.application import WIFI_STATE_CACHE_SECONDS, WebUIPages

    calls = {"n": 0}

    def fake_connectivity():
        calls["n"] += 1
        return "full"

    monkeypatch.setattr(wifi_adapter, "current_network", lambda: "home-net")
    monkeypatch.setattr(wifi_adapter, "connectivity", fake_connectivity)
    pages = WebUIPages("/nonexistent.db", CONFIG)
    assert pages._wifi_available() is True
    assert calls["n"] == 1
    assert pages._wifi_available() is True  # cached
    assert calls["n"] == 1

    # after the cache window it refreshes and reflects a dropped connection
    real_monotonic = time_module.monotonic
    pages._wifi_cache = (real_monotonic() - WIFI_STATE_CACHE_SECONDS - 1, True)
    monkeypatch.setattr(wifi_adapter, "connectivity", lambda: "none")
    assert pages._wifi_available() is False

    # adapter errors mean not available
    def broken():
        raise wifi_adapter.WifiError("nmcli failed")

    pages._wifi_cache = (real_monotonic() - WIFI_STATE_CACHE_SECONDS - 1, True)
    monkeypatch.setattr(wifi_adapter, "connectivity", broken)
    assert pages._wifi_available() is False


def test_review_page_opens_the_database_with_migrations(controller, tmp_path, monkeypatch):
    """Regression: the server thread must migrate-check against the real set."""
    from leo_kiosk.application import WebUIPages
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    db_path = tmp_path / "catalog.sqlite3"
    open_database(db_path, migrations=MIGRATIONS).close()  # launcher-shaped DB
    pages = WebUIPages(db_path, CONFIG)
    html = pages.review()
    assert "Review is unavailable" not in html
    assert "Review games" in html  # empty catalog is fine; the error is not


# --- trial thumbnail capture (Down/Down during a review trial) -----------
def _surface():
    import cairo

    return cairo.ImageSurface(cairo.Format.ARGB32, 1280, 1920)


def _thumb_trial(controller_tuple, game_id):
    """Start a trial with fake catalog/sessions; return (controller, window)."""
    controller, window, _tmp = controller_tuple

    class Entry:
        playable_url = "https://games.example/play"
        display_name = "Game A"

    class Catalog:
        @staticmethod
        def get_entry(_game_id):
            return Entry()

    class Sessions:
        @staticmethod
        def start_trial(_url, _game_id):
            return game_id

        @staticmethod
        def stop(_token, _outcome):
            pass

    controller.catalog = Catalog()
    controller.sessions = Sessions()
    controller.request_web_trial(game_id)
    return controller, window


def test_down_down_during_trial_captures_and_saves(controller, monkeypatch, tmp_path):
    import io

    import cairo

    from leo_kiosk.domain.gestures import GestureAction

    game_id = uuid4()
    controller, window = _thumb_trial(controller, game_id)

    saved = {}

    class FakeWriter:
        def save(self, gid, png_bytes):
            saved["game_id"] = gid
            saved["png"] = png_bytes

    monkeypatch.setattr(controller, "_thumb_writer", lambda: FakeWriter())

    surface = cairo.ImageSurface(cairo.Format.ARGB32, 1280, 1920)
    captures = []
    monkeypatch.setattr(
        window, "capture_snapshot", lambda on_done: (captures.append(1), on_done(surface))[1]
    )
    monkeypatch.setattr(
        window, "toast", lambda message: captures.append(("toast", message))
    )

    controller.on_gesture(GestureAction.SCREENSHOT)

    assert captures[0] == ("toast", "Screenshot captured")  # instant feedback
    assert controller.trial_token is not None  # trial continues
    assert saved["game_id"] == game_id
    out = io.BytesIO(saved["png"])
    resized = cairo.ImageSurface.create_from_png(out)
    assert (resized.get_width(), resized.get_height()) == (800, 400)


def test_screenshot_failure_is_a_silent_noop(controller, monkeypatch):
    from leo_kiosk.domain.gestures import GestureAction

    game_id = uuid4()
    controller, window = _thumb_trial(controller, game_id)

    class FakeWriter:
        def save(self, gid, png_bytes):
            raise ValueError("bad png")

    monkeypatch.setattr(controller, "_thumb_writer", lambda: FakeWriter())
    monkeypatch.setattr(
        window, "capture_snapshot", lambda on_done: on_done(_surface())
    )  # real surface, failing save: the trial must survive

    controller.on_gesture(GestureAction.SCREENSHOT)  # must not raise
    assert controller.trial_token is not None  # trial continues


def test_failed_snapshot_leaves_no_art(controller, monkeypatch):
    from leo_kiosk.domain.gestures import GestureAction

    game_id = uuid4()
    controller, window = _thumb_trial(controller, game_id)
    saved = []

    class FakeWriter:
        def save(self, gid, png_bytes):
            saved.append(gid)

    monkeypatch.setattr(controller, "_thumb_writer", lambda: FakeWriter())
    monkeypatch.setattr(window, "capture_snapshot", lambda on_done: on_done(None))

    controller.on_gesture(GestureAction.SCREENSHOT)
    assert saved == []  # silent no-op on snapshot failure


def test_screenshot_gesture_outside_trial_does_nothing(controller, monkeypatch):
    from leo_kiosk.domain.gestures import GestureAction

    controller, window, _tmp = controller
    monkeypatch.setattr(
        window, "capture_snapshot", lambda on_done: (_ for _ in ()).throw(AssertionError("called"))
    )
    controller.on_gesture(GestureAction.SCREENSHOT)  # no trial: no capture
    assert controller.route is Route.CHILD_HOME


def _homechild_trial(controller_tuple, game_id, slot=3):
    """Start a trial whose Down/Up return is the Home-Child pick list."""
    from leo_kiosk.domain.gestures import GestureAction  # noqa: F401

    controller, window, _tmp = controller_tuple

    class Entry:
        playable_url = "https://games.example/play"
        display_name = "Game A"

    class Catalog:
        @staticmethod
        def get_entry(_game_id):
            return Entry()

    class Sessions:
        @staticmethod
        def start_trial(_url, _game_id):
            return game_id

    controller.catalog = Catalog()
    controller.sessions = Sessions()
    controller.request_web_trial(game_id, "homechild", slot)
    return controller, window


def test_homechild_trial_returns_to_the_pick_list(controller):
    from leo_kiosk.domain.gestures import GestureAction

    game = uuid4()
    controller, window = _homechild_trial(controller, game, slot=3)
    assert controller.trial_return == "homechild"
    assert controller.trial_slot == 3
    assert controller.route is Route.REVIEW_TRIAL

    # Down/Up ends the trial; the finish callback lands on the pick list for
    # the tile the trial came from.
    stopped = []

    class Stopping:
        @staticmethod
        def start_trial(_url, _game_id):
            return game

        @staticmethod
        def stop(token, outcome):
            stopped.append((token, outcome))

    controller.sessions = Stopping()
    controller.on_gesture(GestureAction.RETURN)
    assert stopped == [(game, application.LaunchOutcome.RETURN_GESTURE)]
    controller.trial_finished(game, "return_gesture")
    assert window.navigations[-1] == "http://127.0.0.1:1/homechild/3"

    # a trial without a tile falls back to the Home Child preview
    controller.request_web_trial(game, "homechild")
    controller.trial_finished(game, "return_gesture")
    assert window.navigations[-1] == "http://127.0.0.1:1/homechild"


def test_down_down_during_homechild_trial_captures_nothing(controller):
    from leo_kiosk.domain.gestures import GestureAction

    game = uuid4()
    controller, window = _homechild_trial(controller, game)

    def no_capture(_on_done):
        raise AssertionError("capture_snapshot must not be called")

    window.capture_snapshot = no_capture  # type: ignore[method-assign]
    toasts = list(window.toasts)
    controller.on_gesture(GestureAction.SCREENSHOT)
    assert window.toasts == toasts  # no toast either: a plain try-out
    assert controller.trial_token is not None  # the trial simply continues
    assert controller.trial_game_id == game


def test_homechild_pages_track_the_home_picker_route(controller):
    controller, window, _tmp = controller
    controller.web_navigated("http://127.0.0.1:1/homechild")
    assert controller.route is Route.HOME_PICKER
    controller.web_navigated("http://127.0.0.1:1/homechild/3")
    assert controller.route is Route.HOME_PICKER
    controller.route = Route.PARENT_HOME
    controller.web_navigated("http://127.0.0.1:1/review")
    assert controller.route is Route.REVIEW_LIST


def test_app_exit_records_used_screen_time(controller):
    import time as _time
    from datetime import datetime

    controller, window, _tmp = controller

    recorded = []

    class Usage:
        def record(self, seconds, now):
            recorded.append((seconds, isinstance(now, datetime)))

    controller.usage = Usage()
    controller._on_app_launch()
    _time.sleep(0.05)
    controller._on_app_exit()
    assert len(recorded) == 1
    seconds, has_now = recorded[0]
    assert has_now and seconds > 0

    # a failed spawn (no on_enter) must record nothing on the next exit
    controller._on_app_exit()
    assert len(recorded) == 1

    # and a controller without a usage service must not crash
    controller.usage = None
    controller._on_app_launch()
    controller._on_app_exit()


def test_record_failure_never_blocks_the_exit(controller, monkeypatch, capsys):
    controller, window, _tmp = controller

    class Boom:
        def record(self, seconds, now):
            raise RuntimeError("disk full")

    controller.usage = Boom()
    controller._on_app_launch()
    controller._on_app_exit()  # must not raise; window still shows
    assert window.shown == 1


def _sized_game(controller_tuple, game_id, width, height, evidence="design"):
    """Catalog entry with verified design dimensions for the zoom tests."""
    from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions

    controller, window, _tmp = controller_tuple

    class Entry:
        playable_url = "https://games.example/play"
        display_name = "Game A"
        dimensions = Dimensions(width, height, DimensionEvidence(evidence))

    class Catalog:
        @staticmethod
        def get_entry(_game_id):
            return Entry()

    class Sessions:
        @staticmethod
        def start_trial(_url, _game_id):
            return game_id

    controller.catalog = Catalog()
    controller.sessions = Sessions()
    return controller, window


def test_trial_zoom_fits_a_fixed_size_game(controller):
    game = uuid4()
    controller, window = _sized_game(controller, game, 1024, 768)
    controller.request_web_trial(game)
    # viewport 1280x1920: min(1280/1024, 1920/768) = 1.25
    assert window.zooms[-1] == 1.25

    # finishing the trial restores our own pages to zoom 1
    controller.trial_finished(game, "return_gesture")
    assert window.zooms[-1] == 1.0


def test_trial_without_verified_dimensions_keeps_zoom_1(controller):
    from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions

    game = uuid4()
    controller, window, _tmp = controller
    # metadata-only size (evidence 'inferred'): not trusted for scaling
    controller.catalog = type(
        "C",
        (),
        {"get_entry": staticmethod(lambda _g: type(
            "E", (), {"playable_url": "https://x", "display_name": "G",
                      "dimensions": Dimensions(800, 600, DimensionEvidence.INFERRED)})())},
    )()
    controller.sessions = type("S", (), {"start_trial": staticmethod(lambda u, g: g)})()
    controller.request_web_trial(game)
    assert window.zooms == [1.0]


def test_trial_zoom_scales_down_oversized_games(controller):
    game = uuid4()
    controller, window = _sized_game(controller, game, 3000, 2000)
    controller.request_web_trial(game)
    # min(1280/3000, 1920/2000) = 0.427 -> clamped to the 0.5 lower bound
    assert window.zooms[-1] == 0.5


# --- child game launches from the home screen -------------------------------
def test_request_child_game_runs_in_the_view_and_counts_time(controller):
    game = uuid4()
    controller, window = _sized_game(controller, game, 1024, 768)

    started = []

    class Sessions:
        @staticmethod
        def start_child_game(url, gid, slot, minutes):
            started.append((url, gid, slot, minutes))
            return gid

    controller.sessions = Sessions()
    controller.route = Route.CHILD_HOME
    controller.request_child_game(game, 3, 20)
    assert started == [("https://games.example/play", game, 3, 20)]
    assert controller.route is Route.CHILD_ACTIVITY
    assert controller.trial_return == "child"
    assert window.navigations[-1] == "https://games.example/play"
    assert window.zooms[-1] == 1.25  # fixed-size games still fill the screen
    assert controller._web_usage_started is not None

    # on finish: usage recorded, back to the child home
    recorded = []

    class Usage:
        def record(self, seconds, now, game_id=None):
            recorded.append((seconds, game_id))

    controller.usage = Usage()
    controller.trial_finished(game, "return_gesture")
    assert len(recorded) == 1 and recorded[0][0] > 0
    assert recorded[0][1] == game  # the child game's identity is attributed
    assert controller.route is Route.CHILD_HOME
    assert window.navigations[-1] == "http://127.0.0.1:1/"
    assert window.zooms[-1] == 1.0
    assert controller._web_usage_started is None


def test_request_child_game_is_refused_outside_the_child_home(controller):
    game = uuid4()
    controller, window = _sized_game(controller, game, 1024, 768)
    started = []

    class Sessions:
        @staticmethod
        def start_child_game(url, gid, slot, minutes):
            started.append(1)
            return gid

    controller.sessions = Sessions()
    controller.route = Route.PARENT_HOME
    controller.request_child_game(game, 2, 20)
    assert started == []  # only the child home may start one
