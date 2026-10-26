"""Touch-reactive rainbow background for the child screens.

While a finger presses anywhere on the screen — background or tiles —
horizontal stripes (about 100 px tall) scroll slowly downward. When the
finger lifts, the scroll stops and the stripes fade out. The owning windows
connect this painter to their own ``draw`` handler (which provably runs for
the toplevel) and forward window-level press/release events; returning
False keeps events flowing so tile activation is never consumed.
"""

import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib  # noqa: E402

TICK_MS = 33
SPEED_PX_PER_SECOND = 150.0
STRIPE_HEIGHT = 100
FADE_SECONDS = 1.2
BASE_RGB = (27 / 255, 27 / 255, 47 / 255)  # matches the child screens' CSS
PALETTE = ("#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93", "#ff7ab6")


def fade_alpha(elapsed: float) -> float:
    """Linear fade from fully visible to gone over FADE_SECONDS."""
    return max(0.0, min(1.0, 1.0 - elapsed / FADE_SECONDS))


def parse_palette() -> list[tuple[float, float, float]]:
    """Parse the palette once; drawing reads plain RGB tuples."""
    out = []
    for spec in PALETTE:
        rgba = Gdk.RGBA()
        if not rgba.parse(spec):
            raise ValueError(f"Unparseable rainbow color: {spec}")
        out.append((rgba.red, rgba.green, rgba.blue))
    return out


def wire_rainbow(painter, *widgets) -> None:
    """Forward press/release from the widgets that actually receive them.

    Returning False keeps the event flowing, so tile activation on release
    is never consumed; double-delivery (bubble + direct) is harmless because
    the painter state machine is idempotent.
    """
    for widget in widgets:
        widget.connect(
            "button-press-event", lambda *_: painter.start_scroll() or False
        )
        widget.connect(
            "button-release-event", lambda *_: painter.stop_scroll() or False
        )


class RainbowPainter:
    """State machine + painter; the owning window calls paint from its draw."""

    def __init__(self, invalidate, clock=time.monotonic):
        self.invalidate = invalidate
        self.clock = clock
        self.colors = parse_palette()
        self.offset = 0.0
        self.scroll_start = 0.0
        self.scroll_anchor = 0.0
        self.scrolling = False
        self.fading_since: float | None = None
        self.tick_scheduled = False
        self._tick_announced = False
        self._paint_announced = False

    # --- screen-driven gestures -------------------------------------------
    def start_scroll(self) -> None:
        """Begin (or resume) the downward scroll; called on any press."""
        print("rainbow: press", flush=True)
        self.scrolling = True
        self.fading_since = None
        self.scroll_anchor = self.offset
        self.scroll_start = self.clock()
        self.schedule_tick()

    def stop_scroll(self) -> None:
        """Stop the scroll and fade out; called on finger lift."""
        if not self.scrolling:
            return
        print("rainbow: release", flush=True)
        self.scrolling = False
        self.fading_since = self.clock()
        self.schedule_tick()

    def reset(self) -> None:
        """Drop all state; called when the owning window is hidden."""
        self.scrolling = False
        self.fading_since = None
        self.offset = 0.0
        self.tick_scheduled = False

    def schedule_tick(self) -> None:
        if not self.tick_scheduled:
            self.tick_scheduled = True
            GLib.timeout_add(TICK_MS, self.tick)

    def tick(self) -> bool:
        """Advance scroll or fade; keep ticking while either is active."""
        self.tick_scheduled = False
        if not self._tick_announced:
            print(
                f"rainbow: tick scrolling={self.scrolling} "
                f"fading={self.fading_since is not None} offset={self.offset:.1f}",
                flush=True,
            )
            self._tick_announced = True
        if self.scrolling:
            self.offset = self.scroll_anchor + (
                self.clock() - self.scroll_start
            ) * SPEED_PX_PER_SECOND
            self.invalidate()
            self.tick_scheduled = True
            return True
        if self.fading_since is not None:
            if fade_alpha(self.clock() - self.fading_since) <= 0.0:
                self.fading_since = None
                self.invalidate()
                return False
            self.invalidate()
            self.tick_scheduled = True
            return True
        return False

    # --- painting ---------------------------------------------------------
    def paint(self, cr, width: int, height: int) -> None:
        """Base fill plus scrolling stripes; called from the window's draw."""
        if not self._paint_announced:
            print(
                f"rainbow: painted w={width} h={height} offset={self.offset:.1f} "
                f"scrolling={self.scrolling}",
                flush=True,
            )
            self._paint_announced = True
        cr.set_source_rgb(*BASE_RGB)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        alpha = 1.0
        if self.fading_since is not None:
            alpha = fade_alpha(self.clock() - self.fading_since)
        if alpha <= 0.0 or not (self.scrolling or self.fading_since is not None):
            return  # idle: base color only, never stripes
        first_band = int(self.offset // STRIPE_HEIGHT)
        last_band = int((self.offset + height) // STRIPE_HEIGHT)
        for band in range(first_band, last_band + 1):
            top = band * STRIPE_HEIGHT - self.offset
            r, g, b = self.colors[band % len(self.colors)]
            cr.set_source_rgba(r, g, b, alpha)
            cr.rectangle(0, top, width, STRIPE_HEIGHT)
            cr.fill()