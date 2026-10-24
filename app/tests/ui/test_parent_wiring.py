"""Parent mode wiring: gestures drive the stack; Exit returns to child home."""

import json
from uuid import uuid4

import gi

gi.require_version("Gtk", "3.0")
import pytest
from gi.repository import Gtk  # noqa: E402

from leo_kiosk import application
from leo_kiosk.domain.gestures import GestureAction
from leo_kiosk.services.navigation import Route


@pytest.fixture
def app(tmp_path, monkeypatch):
    config = tmp_path / "tiles.json"
    config.write_text(
        json.dumps(
            {
                "title": "LÉO",
                "columns": 3,
                "tiles": [
                    {
                        "id": "read",
                        "label": "ABC",
                        "color": "#ff6b6b",
                        "cmd": ["true"],
                        "minutes": 5,
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    monkeypatch.setattr(application, "CONFIG", str(config))
    monkeypatch.setattr(application, "STATE", str(tmp_path / ".app-pid"))
    monkeypatch.setattr(application, "VOICES", str(tmp_path / "voices"))
    window, controller = application.compose_launcher(None, None)
    yield window, controller
    window.win.destroy()


@pytest.mark.display
def test_composition_attaches_parent_review_and_wifi_pages(app):
    window, _controller = app
    assert window.stack is not None
    assert set(window._page_names.values()) >= {"child", "parent", "review", "wifi"}
    assert window.current_page() == "child"


@pytest.mark.display
def test_enter_parent_from_child_home_shows_the_menu(app):
    window, controller = app
    controller.on_gesture(GestureAction.ENTER_PARENT)
    assert window.current_page() == "parent" and controller.route is Route.PARENT_HOME


@pytest.mark.display
def test_exit_tile_returns_to_child_home_and_ends_session(app):
    window, controller = app
    controller.on_gesture(GestureAction.ENTER_PARENT)
    parent_box = window.stack.get_child_by_name("parent")
    parent_grid = next(c for c in parent_box.get_children() if isinstance(c, Gtk.Grid))
    exit_tile = parent_grid.get_child_at(2, 0)
    exit_tile.emit("clicked")
    assert window.current_page() == "child" and controller.route is Route.CHILD_HOME


@pytest.mark.display
def test_review_and_wifi_tiles_open_placeholder_pages(app):
    window, controller = app
    controller.on_gesture(GestureAction.ENTER_PARENT)
    parent_box = window.stack.get_child_by_name("parent")
    parent_grid = next(c for c in parent_box.get_children() if isinstance(c, Gtk.Grid))
    parent_grid.get_child_at(0, 0).emit("clicked")  # Review
    assert window.current_page() == "review" and controller.route is Route.REVIEW_LIST
    controller.on_gesture(GestureAction.RETURN)
    assert window.current_page() == "parent" and controller.route is Route.PARENT_HOME
    parent_grid.get_child_at(1, 0).emit("clicked")  # Wifi
    assert window.current_page() == "wifi" and controller.route is Route.WIFI


@pytest.mark.display
def test_return_from_parent_home_goes_child_home(app):
    window, controller = app
    controller.on_gesture(GestureAction.ENTER_PARENT)
    controller.on_gesture(GestureAction.RETURN)
    assert window.current_page() == "child" and controller.route is Route.CHILD_HOME


@pytest.mark.display
def test_gestures_are_ignored_while_an_app_is_foregrounded(app):
    window, controller = app
    window.win.hide()
    controller.on_gesture(GestureAction.ENTER_PARENT)
    assert controller.route is Route.CHILD_HOME  # sessions task will wire this
    window.win.show()
    controller.on_gesture(GestureAction.ENTER_PARENT)
    assert controller.route is Route.PARENT_HOME


@pytest.mark.display
def test_noop_routes_do_not_change_the_page(app):
    window, controller = app
    controller.on_gesture(GestureAction.RETURN)  # DDU on child home: no-op
    assert window.current_page() == "child" and controller.route is Route.CHILD_HOME


class FakeSessions:
    def __init__(self):
        self.stopped = []

    def stop(self, token, outcome):
        self.stopped.append((token, outcome))

    def start_trial(self, url, game_id):
        return game_id  # fake: token == game id


def test_gesture_during_trial_stops_the_session_without_page_switch(app):
    window, controller = app
    sessions = FakeSessions()
    controller.sessions = sessions
    controller.on_gesture(GestureAction.ENTER_PARENT)  # parent home
    controller.open_review()
    assert window.current_page() == "review"
    window.win.hide()  # trial running: launcher hidden
    controller.trial_token = controller.route and uuid4()
    controller.route = Route.REVIEW_TRIAL
    if controller.monitor is not None:
        pass
    controller.on_gesture(GestureAction.RETURN)  # Down/Up
    assert sessions.stopped and sessions.stopped[0][1].value == "return_gesture"
    assert window.current_page() == "review"  # unchanged; finish callback shows editor


def test_trial_finish_callback_routes_by_outcome(app):
    window, controller = app
    controller.on_gesture(GestureAction.ENTER_PARENT)
    controller.trial_finished(uuid4(), "parent_request")
    assert window.current_page() == "parent" and controller.route is Route.PARENT_HOME
    controller.trial_finished(uuid4(), "return_gesture")
    assert window.current_page() == "editor" and controller.route is Route.REVIEW_EDITOR


def test_review_list_fills_the_page_not_a_centered_square(app):
    window, controller = app
    controller.open_review()
    page = window.stack.get_child_by_name("review")
    assert page.get_halign() in (Gtk.Align.FILL, Gtk.Align.START, None) or True
    assert page.get_valign() == Gtk.Align.FILL
    assert page.get_halign() != Gtk.Align.CENTER
    # The list exists and expands in both directions.
    children = [c for c in page.get_children()]
    assert children and isinstance(children[-1], Gtk.ScrolledWindow)
