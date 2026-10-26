"""Kiosk launcher window: big picture tiles, one app at a time, auto-return home.

Extracted from the legacy launcher.py without behavior change. Seams are
injected for tests: process spawning, clock, sound player and exit hook.
"""

import json
import os
import signal
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")  # pin 3.x; gtk4's Gdk 4.0 must not load first
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from leo_kiosk.ui.battery import BatteryMonitor, paint_gauge  # noqa: E402
from leo_kiosk.ui.rainbow import RainbowPainter, wire_rainbow  # noqa: E402

TAP_SOUND = "/usr/share/sounds/freedesktop/stereo/message.oga"

# Fixed tile geometry, shared by the home and Videos screens so both grids
# render pixel-identical tiles regardless of surrounding labels.
TILE_HEIGHT = 300
GRID_HEIGHT = 3 * TILE_HEIGHT + 2 * 20  # three rows plus the grid's spacing

CSS = b"""
window { background: transparent; }
.title { color: white; font-size: 44px; font-weight: 800; }
.status { color: #ffd43b; font-size: 28px; font-weight: 700; }
.battery { color: white; font-size: 30px; font-weight: 700; }
.battery-low { color: #ff6b6b; }
.tile { border-radius: 36px; border: none; box-shadow: none; padding: 0; }
.tile label.word { font-size: 44px; font-weight: 800; color: #1b1b2f; }
"""


def play(path):
    if os.path.exists(path):
        try:
            subprocess.Popen(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


class LauncherWindow:
    """The child home screen. Invariant: at most one launched app at a time."""

    def __init__(
        self,
        config_path,
        state_path,
        voices_dir,
        popen=subprocess.Popen,
        clock=time.time,
        player=play,
        on_corner_exit=Gtk.main_quit,
    ):
        with open(config_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.state_path = state_path
        self.voices_dir = voices_dir
        self.popen = popen
        self.clock = clock
        self.player = player
        self.on_corner_exit = on_corner_exit
        self.proc = None
        self.deadline = 0.0
        self.corner_taps = []

        self._on_launch_started = None
        self._on_launch_ended = None
        self.win = Gtk.Window()
        self.win.connect("destroy", Gtk.main_quit)
        self.win.set_title("Leo")

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(24)

        title = Gtk.Label(label=self.cfg.get("title", ""))
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)

        grid = Gtk.Grid(
            row_spacing=20, column_spacing=20, row_homogeneous=True, column_homogeneous=True
        )
        grid.set_size_request(-1, GRID_HEIGHT)
        grid.set_halign(Gtk.Align.FILL)
        cols = self.cfg.get("columns", 3)
        for i, tile in enumerate(self.cfg["tiles"]):
            grid.attach(self.make_tile(tile), i % cols, i // cols, 1, 1)
        box.pack_start(title, False, False, 0)
        self.status = Gtk.Label(label="")
        self.status.get_style_context().add_class("status")
        box.pack_end(self.status, False, False, 0)
        box.set_center_widget(grid)

        # Invisible parent corner, on top of everything. The rainbow is not a
        # widget: it is painted from the toplevel draw handler (on_window_draw),
        # because a child layer's draw never fired under the overlay.
        self.rainbow = RainbowPainter(invalidate=self.win.queue_draw)
        self.battery = BatteryMonitor(invalidate=self.win.queue_draw)
        overlay = Gtk.Overlay()
        overlay.add(box)
        corner = Gtk.Button()
        corner.set_size_request(110, 110)
        corner.set_halign(Gtk.Align.START)
        corner.set_valign(Gtk.Align.START)
        corner.set_opacity(0.0)
        corner.connect("clicked", self.on_corner)
        overlay.add_overlay(corner)

        self.win.add(overlay)
        # Rainbow reacts to any touch, including on tiles; False keeps the
        # event flowing so tile activation is never consumed. Each button is
        # wired directly: bubbling from children to the toplevel proved
        # unreliable on-device.
        self.win.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
        )
        self.win.connect("draw", self.on_window_draw)
        wire_rainbow(self.rainbow, self.win, *grid.get_children(), corner)
        self.win.fullscreen()
        self.win.show_all()
        self.stack: Gtk.Stack | None = None
        self._content = overlay
        self._page_names: dict[object, str] = {}

    def on_window_draw(self, _win, cr):
        """Paint the rainbow, then the battery gauge, before children render."""
        width = self.win.get_allocated_width()
        self.rainbow.paint(cr, width, self.win.get_allocated_height())
        paint_gauge(cr, width, self.battery.reading)
        return False

    # --- route pages (parent mode); no-op unless pages were attached -----
    def attach_pages(self, pages: dict[str, Gtk.Widget]) -> None:
        """Wrap the child content in a stack with named pages for parent mode."""
        if self.stack is not None:
            raise RuntimeError("Route pages already attached")
        self.win.remove(self._content)
        self.stack = Gtk.Stack(visible=True, transition_type=Gtk.StackTransitionType.NONE)
        self.stack.add_named(self._content, "child")
        for name, widget in pages.items():
            self.stack.add_named(widget, name)
        self.win.add(self.stack)
        self.win.show_all()
        self._page_names = {widget: name for name, widget in pages.items()}
        self._page_names[self._content] = "child"

    def show_page(self, name: str) -> None:
        if self.stack is None:
            return
        self.stack.set_visible_child_name(name)

    def current_page(self) -> str:
        if self.stack is None:
            return "child"
        child = self.stack.get_visible_child()
        return self._page_names.get(child, "child")

    def is_showing(self) -> bool:
        return self.win.get_visible()

    # --- route-page hooks (inert unless composed) --------------------------
    def set_launch_state_callback(self, on_launch_started, on_launch_ended) -> None:
        """Notified when a legacy tile starts/stops foregrounding an app."""
        self._on_launch_started = on_launch_started
        self._on_launch_ended = on_launch_ended

    # --- tiles ----------------------------------------------------------
    def make_tile(self, tile):
        from leo_kiosk.ui.tile_grid import TileSpec, make_tile_button

        spec = TileSpec(
            label=tile["label"],
            color=tile["color"],
            on_activate=lambda t=tile: self.launch(t),
        )
        return make_tile_button(spec)

    # --- parent corner ---------------------------------------------------
    def on_corner(self, _btn):
        now = self.clock()
        self.corner_taps = [t for t in self.corner_taps if now - t < 4] + [now]
        if len(self.corner_taps) >= 5:
            self.on_corner_exit()

    # --- status ----------------------------------------------------------
    def say(self, text, seconds=3):
        self.status.set_text(text)
        GLib.timeout_add_seconds(seconds, lambda: self.status.set_text("") or False)

    # --- launching -------------------------------------------------------
    def launch(self, tile):
        if self.proc and self.proc.poll() is None:
            return
        voice = None
        for ext in (".wav", ".ogg", ".oga", ".mp3"):
            p = os.path.join(self.voices_dir, tile["id"] + ext)
            if os.path.exists(p):
                voice = p
                break
        self.player(voice or TAP_SOUND)

        home = os.path.expanduser("~")
        candidates = [tile["cmd"]] + ([tile["alt"]] if tile.get("alt") else [])
        self.proc = None
        for raw in candidates:
            cmd = [os.path.expanduser(a).replace("file://~", "file://" + home) for a in raw]
            try:
                self.proc = self.popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                break
            except OSError:
                continue
        if self.proc is None:
            print(f"launch failed for {candidates}", file=sys.stderr, flush=True)
            self.say("Ask Papa to fix this one!")
            return
        self.deadline = self.clock() + tile.get("minutes", 20) * 60
        self.rainbow.reset()  # window is about to hide; drop mid-gesture state
        if self._on_launch_started is not None:
            self._on_launch_started()
        try:
            fd = os.open(self.state_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(str(self.proc.pid))
        except OSError:
            pass
        self.win.hide()
        GLib.timeout_add(500, self.watch)

    def watch(self):
        if self.proc.poll() is not None:
            self.back_home()
            return False
        if self.clock() > self.deadline:
            self.kill_group(signal.SIGTERM)
            GLib.timeout_add_seconds(3, self.force_kill)
            return False
        return True

    def kill_group(self, sig):
        try:
            os.killpg(self.proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def force_kill(self):
        if self.proc.poll() is None:
            self.kill_group(signal.SIGKILL)
        self.back_home()
        return False

    def back_home(self):
        if self._on_launch_ended is not None:
            self._on_launch_ended()
        try:
            os.remove(self.state_path)
        except OSError:
            pass
        self.win.show_all()
        self.win.fullscreen()
        self.win.present()
        self.player(TAP_SOUND)
