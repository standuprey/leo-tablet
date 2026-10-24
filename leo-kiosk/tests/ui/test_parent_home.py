"""Parent menu: nine grey tiles, three active labels, safe Exit."""

import gi

gi.require_version("Gtk", "3.0")
import pytest
from gi.repository import Gtk  # noqa: E402

from leo_kiosk.ui.parent_home import ACTIVE_TILES, build_parent_home, build_parent_screen


@pytest.mark.display
def test_nine_tiles_three_labels_six_blanks():
    calls = {"review": 0, "wifi": 0, "exit": 0}
    grid = build_parent_home(
        lambda: calls.__setitem__("review", calls["review"] + 1),
        lambda: calls.__setitem__("wifi", calls["wifi"] + 1),
        lambda: calls.__setitem__("exit", calls["exit"] + 1),
    )
    children = grid.get_children()
    assert len(children) == 9
    # Grid children are unordered; the first three positions hold the labels.
    active = [grid.get_child_at(i % 3, i // 3) for i in range(3)]
    inactive = [c for c in children if not c.get_sensitive()]
    assert [b.get_child().get_label() for b in active] == list(ACTIVE_TILES)
    assert len(inactive) == 6
    assert all(not b.get_can_focus() for b in inactive)
    assert all(b.get_style_context().has_class("tile-parent") for b in active)


@pytest.mark.display
def test_callbacks_fire_on_click():
    calls = []
    grid = build_parent_home(
        lambda: calls.append("review"), lambda: calls.append("wifi"), lambda: calls.append("exit")
    )
    for i in range(3):  # positions are ordered; get_children() is not
        grid.get_child_at(i % 3, i // 3).emit("clicked")
    assert calls == ["review", "wifi", "exit"]


@pytest.mark.display
def test_exit_callback_is_not_gtk_main_quit(monkeypatch):
    # The exit tile must navigate; quitting the loop would end the kiosk.
    quits = []
    monkeypatch.setattr(Gtk, "main_quit", lambda: quits.append(True))
    calls = []
    grid = build_parent_home(lambda: None, lambda: None, lambda: calls.append("nav"))
    exit_tile = next(
        c for c in grid.get_children() if c.get_sensitive() and c.get_child().get_label() == "Exit"
    )
    exit_tile.emit("clicked")
    assert calls == ["nav"] and quits == []


@pytest.mark.display
def test_screen_includes_retro_title():
    box = build_parent_screen(lambda: None, lambda: None, lambda: None)
    labels = [c for c in box.get_children() if isinstance(c, Gtk.Label)]
    assert labels and labels[0].get_text() == "PARENT"
    assert labels[0].get_style_context().has_class("parent-title")


@pytest.mark.display
def test_grey_parent_tiles_have_no_inline_color():
    grid = build_parent_home(lambda: None, lambda: None, lambda: None)
    for button in (c for c in grid.get_children() if c.get_sensitive()):
        css_classes = button.get_style_context().list_classes()
        assert "tile-parent" in css_classes and "tile-child" not in css_classes


def test_callbacks_are_required():
    with pytest.raises(ValueError):
        build_parent_home(None, lambda: None, lambda: None)
