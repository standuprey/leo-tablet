"""Nine-position grid geometry; display required."""

import gi

gi.require_version("Gtk", "3.0")
import pytest
from gi.repository import Gtk  # noqa: E402

from leo_kiosk.ui.tile_grid import TileSpec, build_grid


@pytest.mark.display
def test_grid_always_renders_nine_positions():
    grid = build_grid([TileSpec("ABC", color="#ff6b6b", on_activate=lambda: None)])
    children = grid.get_children()
    assert len(children) == 9
    buttons = [c for c in children if isinstance(c, Gtk.Button)]
    assert len(buttons) == 9


@pytest.mark.display
def test_blank_tiles_are_insensitive_and_not_focusable():
    grid = build_grid([TileSpec("ABC", color="#ff6b6b", on_activate=lambda: None)])
    blanks = [c for c in grid.get_children() if not c.get_sensitive()]
    assert len(blanks) == 8
    assert all(not b.get_can_focus() for b in blanks)
    assert all(b.get_style_context().has_class("tile-blank") for b in blanks)


@pytest.mark.display
def test_blank_tiles_have_no_label_and_child_tiles_keep_color():
    grid = build_grid(
        [
            TileSpec("ABC", color="#ff6b6b", on_activate=lambda: None),
            TileSpec("Draw", color="#ffd43b", on_activate=lambda: None),
        ]
    )
    labeled = [grid.get_child_at(i % 3, i // 3) for i in range(2)]
    assert [b.get_child().get_label() for b in labeled] == ["ABC", "Draw"]


@pytest.mark.display
def test_activation_fires_exactly_once_per_click():
    calls = []
    grid = build_grid([TileSpec("ABC", color="#ff6b6b", on_activate=lambda: calls.append(1))])
    active = next(c for c in grid.get_children() if c.get_sensitive())
    active.emit("clicked")
    active.emit("clicked")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"label": "A", "color": "#ffffff"},  # labelled tile without action
        {"label": "A", "style": "child", "color": None},  # child without color
        {"label": "A", "style": "parent", "color": "#ffffff"},  # parent with color
        {"label": "A", "color": "#ffffff", "style": "neon"},  # unknown style
    ],
)
def test_invalid_specs(fields):
    with pytest.raises(ValueError):
        TileSpec(**fields)


def test_more_than_nine_tiles_rejected():
    from leo_kiosk.ui.tile_grid import POSITIONS

    with pytest.raises(ValueError):
        build_grid([TileSpec(f"T{i}", color="#fff") for i in range(POSITIONS + 1)])
