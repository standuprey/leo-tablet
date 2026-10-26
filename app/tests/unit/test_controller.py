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


def test_five_corner_taps_quit_the_kiosk(controller):
    controller, _window, _tmp = controller
    quits = []
    controller.launcher.on_corner_exit = lambda: quits.append(1)
    for _ in range(5):
        controller.corner_tap()
    assert quits == [1]


def test_trial_finish_shows_the_interim_state_page(controller):
    controller, window, _tmp = controller
    game = uuid4()
    controller.trial_finished(game, "return_gesture")
    assert controller.route is Route.PARENT_HOME
    assert window.navigations == [f"http://127.0.0.1:1/review/{game}"]
    assert window.shown == 1


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
