"""Videos kiosk screen: nine random videos, Firefox kiosk playback.

Spawned by the launcher's Videos tile as its own script (videos.py) so
leopowerd's kill guard sees a dedicated argv[0] instead of a generic
interpreter. Playback runs in the same process group (no new session), so
both exit gestures — volume down-then-up (backwatch) and the power button
(leopowerd) — tear down playback and return to the home grid. A video that
ends on its own returns to this grid.
"""

import json
import os
import random
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")  # pin 3.x; gtk4's Gdk 4.0 must not load first
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from leo_kiosk.ui.rainbow import RainbowPainter, wire_rainbow  # noqa: E402
from leo_kiosk.ui.tile_grid import TileSpec, build_grid  # noqa: E402
from leo_kiosk.ui.window import CSS, GRID_HEIGHT  # noqa: E402

MAX_TILES = 9
MPV = "mpv"
WATCH_INTERVAL_MS = 500
LABEL_LIMIT = 70
TILE_COLORS = (
    "#ff6b6b", "#4dabf7", "#20c997", "#f783ac", "#b197fc",
    "#ffa94d", "#ffd43b", "#82c91e", "#ff8787",
)


def load_videos(path: str) -> list[dict[str, object]]:
    """Load the trusted video catalog; reject partial or malformed entries."""
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read video catalog {path}: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"Video catalog {path} must be a nonempty list")
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError(f"Video catalog entry must be an object: {entry!r}")
        title = entry.get("title")
        embed = entry.get("embed_url")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Video entry missing title: {entry!r}")
        if not isinstance(embed, str) or not embed.startswith(("http://", "https://")):
            raise ValueError(f"Video entry missing HTTP(S) embed_url: {entry!r}")
    return data


def sample_videos(
    videos: list[dict[str, object]], rng: random.Random, count: int = MAX_TILES
) -> list[dict[str, object]]:
    """Pick random videos for the grid; fewer entries mean a smaller grid."""
    return rng.sample(videos, min(count, len(videos)))


def tile_label(video: dict[str, object]) -> str:
    """ASCII-only title, cut at the first pipe, capped for the tile shape."""
    title = str(video.get("title") or "").split("|", 1)[0]
    title = "".join(c for c in title if 32 <= ord(c) < 127)
    title = " ".join(title.split())
    if not title:
        return "..."
    return title if len(title) <= LABEL_LIMIT else title[: LABEL_LIMIT - 1] + "..."


class VideosWindow:
    """One child-facing screen: 3x3 video tiles, at most one playback."""

    def __init__(self, catalog_path: str, popen=subprocess.Popen, clock=time.time):
        self.popen = popen
        self.clock = clock
        self.proc = None
        try:
            # mpv's own output must be visible for on-device diagnosis.
            self.play_log = open("/tmp/leo-videos.log", "a", buffering=1)
        except OSError:
            self.play_log = None
        self.videos = sample_videos(load_videos(catalog_path), random.Random())

        self.win = Gtk.Window()
        self.win.connect("destroy", Gtk.main_quit)
        self.win.set_title("VIDEOS")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(24)
        # Empty title/status slots mirror the home screen's vertical budget,
        # so video tiles come out exactly home-tile sized.
        title = Gtk.Label(label="")
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)
        specs = [
            TileSpec(
                label=tile_label(video),
                color=TILE_COLORS[i % len(TILE_COLORS)],
                on_activate=lambda v=video: self.play(v),
            )
            for i, video in enumerate(self.videos)
        ]
        grid = build_grid(specs)
        grid.set_size_request(-1, GRID_HEIGHT)
        grid.set_halign(Gtk.Align.FILL)
        box.set_center_widget(grid)
        # Same painter-in-window-draw contract as the home screen; a child
        # layer's draw never fired under the overlay there.
        self.rainbow = RainbowPainter(invalidate=self.win.queue_draw)
        overlay = Gtk.Overlay()
        overlay.add(box)
        self.win.add(overlay)
        self.win.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
        )
        self.win.connect("draw", self.on_window_draw)
        wire_rainbow(self.rainbow, self.win, *grid.get_children())

    def on_window_draw(self, _win, cr):
        """Paint the rainbow background before the default handler propagates."""
        self.rainbow.paint(
            cr, self.win.get_allocated_width(), self.win.get_allocated_height()
        )
        return False

    def play(self, video: dict[str, object]) -> None:
        """Fullscreen mpv playback; same process group, so gestures still exit."""
        if self.proc is not None and self.proc.poll() is None:
            return
        # YouTube embeds (top-level or iframe) die with player error 153;
        # mpv + yt-dlp plays the watch URL fullscreen with no web context.
        # Note: mpv 0.41 dropped --play-and-exit; --keep-open=no is the same
        # behavior, and --no-terminal is omitted so errors reach the log.
        url = str(video.get("watch_url") or video["embed_url"])
        try:
            self.proc = self.popen(
                [
                    MPV,
                    "--fullscreen",
                    "--keep-open=no",
                    "--hwdec=auto",
                    "--ytdl-format=best[height<=?1080]",
                    "--script-opts=ytdl_hook-ytdl_path=yt-dlp",
                    url,
                ],
                stdout=self.play_log or subprocess.DEVNULL,
                stderr=self.play_log or subprocess.DEVNULL,
            )
        except OSError as exc:
            self.show_error(f"Cannot play this one: {exc}")
            return
        self.rainbow.reset()  # window is about to hide; drop mid-gesture state
        self.win.hide()
        GLib.timeout_add(WATCH_INTERVAL_MS, self.watch)

    def watch(self) -> bool:
        """Reshow the grid when playback ends; the home launcher owns limits."""
        if self.proc is not None and self.proc.poll() is not None:
            self.proc = None
            self.win.show_all()
            return False
        return True

    def show_error(self, text: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.win, modal=True, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE, text=text,
        )
        dialog.run()
        dialog.destroy()

    def run(self) -> None:
        self.win.fullscreen()
        self.win.show_all()
        Gtk.main()


def main() -> None:
    # __file__ is <root>/leo_kiosk/ui/videos_window.py; the catalog lives at
    # <root>/kiosk_videos.json (kiosk root on the device, app/ in dev).
    package_parent = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    candidates = [
        os.environ.get("LEO_VIDEOS_CATALOG"),
        os.path.join(package_parent, "kiosk_videos.json"),
    ]
    catalog = next((c for c in candidates if c and os.path.exists(c)), None)
    if catalog is None:
        print(
            "videos: no catalog found (looked for LEO_VIDEOS_CATALOG and "
            f"{os.path.join(package_parent, 'kiosk_videos.json')})",
            file=sys.stderr,
        )
        raise SystemExit(1)
    window = VideosWindow(catalog)
    print(
        f"videos screen: catalog={catalog} videos={len(window.videos)}",
        file=sys.stderr,
        flush=True,
    )
    window.run()