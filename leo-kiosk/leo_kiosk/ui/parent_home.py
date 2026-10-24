"""Parent home: nine grey tiles, Review/Wifi/Exit active, six inert blanks.

Retro terminal look: near-black background, amber text, square grey tiles
(Apple-IIc inspired, deliberately not green). Exit is navigation only — it
must never quit the GTK main loop or the kiosk session.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from .tile_grid import POSITIONS, TileSpec, build_grid  # noqa: E402

CSS = b"""
window, stack { background: #0f0f10; }
.parent-title {
  color: #ffb000; font-family: Monospace; font-size: 40px;
  font-weight: 700; letter-spacing: 8px;
}
.tile-parent button {
  background: #2e2e2e; border: 2px solid #8a8a8a; border-radius: 0;
  color: #ffb000; font-family: Monospace; font-size: 38px; font-weight: 700;
}
.tile-parent button:active { background: #4a4a4a; }
.tile-blank { background: #1a1a1a; border: 2px solid #3a3a3a; border-radius: 0; }
"""

ACTIVE_TILES = ("Review", "Wifi", "Exit")


def apply_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def build_parent_home(on_review, on_wifi, on_exit) -> Gtk.Grid:
    """Return the parent menu grid; callbacks own navigation decisions."""
    for callback in (on_review, on_wifi, on_exit):
        if not callable(callback):
            raise ValueError("Parent menu requires navigation callbacks")
    specs = [
        TileSpec(label, style="parent", on_activate=callback)
        for label, callback in zip(ACTIVE_TILES, (on_review, on_wifi, on_exit), strict=True)
    ]
    specs += [TileSpec(label="", style="parent") for _ in range(POSITIONS - len(specs))]
    return build_grid(specs)


def build_parent_screen(on_review, on_wifi, on_exit) -> Gtk.Box:
    """Fullscreen parent surface: title above the menu grid."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_border_width(24)
    title = Gtk.Label(label="PARENT")
    title.get_style_context().add_class("parent-title")
    box.pack_start(title, False, False, 0)
    box.pack_start(build_parent_home(on_review, on_wifi, on_exit), True, True, 0)
    return box
