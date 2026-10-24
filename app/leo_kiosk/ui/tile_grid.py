"""Shared nine-position tile geometry for child and parent screens.

Widgets render immutable tile models; they never own business logic.
"""

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

POSITIONS = 9
COLUMNS = 3


@dataclass(frozen=True)
class TileSpec:
    label: str
    color: str | None = None
    on_activate: Callable[[], None] | None = None
    style: str = "child"  # "child" (colored) or "parent" (grey)

    def __post_init__(self) -> None:
        if self.style not in ("child", "parent"):
            raise ValueError("Tile style must be child or parent")
        if not isinstance(self.label, str):
            raise ValueError("Tile label must be a string")
        if self.label.strip() and self.on_activate is None:
            raise ValueError("A labelled tile must be actionable")
        if not self.label.strip() and self.on_activate is not None:
            raise ValueError("A blank tile must not be actionable")
        if self.style == "child" and self.color is None:
            raise ValueError("Child tiles require a color")
        if self.style == "parent" and self.color is not None:
            raise ValueError("Parent tiles are grey and take no color")


def build_grid(tiles: list[TileSpec]) -> Gtk.Grid:
    """Render exactly nine positions; blanks are inert and not focusable."""
    if len(tiles) > POSITIONS:
        raise ValueError("At most nine tiles")
    grid = Gtk.Grid(
        row_spacing=20, column_spacing=20, row_homogeneous=True, column_homogeneous=True
    )
    rendered = 0
    for spec in tiles:
        grid.attach(_tile_button(spec), rendered % COLUMNS, rendered // COLUMNS, 1, 1)
        rendered += 1
    for position in range(rendered, POSITIONS):
        blank = Gtk.Button(sensitive=False, can_focus=False)
        blank.get_style_context().add_class("tile-blank")
        blank.set_hexpand(True)
        blank.set_vexpand(True)
        grid.attach(blank, position % COLUMNS, position // COLUMNS, 1, 1)
    return grid


def _tile_button(spec: TileSpec) -> Gtk.Button:
    button = Gtk.Button()
    context = button.get_style_context()
    context.add_class("tile")
    context.add_class(f"tile-{spec.style}")
    css = Gtk.CssProvider()
    background = spec.color if spec.style == "child" else None
    if background:
        css.load_from_data(f"button {{ background: {background}; }}".encode())
        context.add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    label = Gtk.Label(label=spec.label)
    label.get_style_context().add_class("word")
    label.set_line_wrap(True)
    label.set_justify(Gtk.Justification.CENTER)
    button.add(label)
    if spec.on_activate is not None:
        button.connect("clicked", lambda _b: spec.on_activate())
    else:
        button.set_sensitive(False)
        button.set_can_focus(False)
    button.set_hexpand(True)
    button.set_vexpand(True)
    return button
