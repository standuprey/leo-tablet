"""Battery gauge for the home screen: sysfs reading + toplevel-draw painting.

The gauge is not a widget: like the rainbow, it is painted from the owning
window's draw handler (the only draw path proven to run under the kiosk).
Geometry: 120x25 px, 2 px white border, 3 px radius, filled light purple to
the remaining capacity, top-right and vertically aligned with the title.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # noqa: E402

POWER_SUPPLY = "/sys/class/power_supply"
REFRESH_SECONDS = 60

GAUGE_WIDTH = 120
GAUGE_HEIGHT = 25
GAUGE_RADIUS = 3
GAUGE_BORDER = 2
GAUGE_TOP = 37  # vertically centered on the 44px title line
GAUGE_RIGHT_MARGIN = 30  # aligns the gauge's outer edge with the tile grid
GAUGE_FILL_RGB = (0.694, 0.592, 0.988)  # light purple #b197fc
BOLT_RGB = (1.0, 0.831, 0.231)  # charging bolt #ffd43b
BOLT_WIDTH = 14
BOLT_HEIGHT = 22
BOLT_POINTS = ((8, 0), (2, 13), (6, 13), (0, 22), (13, 8), (7, 8), (11, 0))


def read_battery(root: str = POWER_SUPPLY) -> tuple[int, bool] | None:
    """Return (capacity percent, charging) for the first battery, or None."""
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    for name in entries:
        base = os.path.join(root, name)
        try:
            with open(os.path.join(base, "type"), encoding="utf-8") as f:
                if f.read().strip() != "Battery":
                    continue
            with open(os.path.join(base, "capacity"), encoding="utf-8") as f:
                capacity = int(f.read().strip())
            with open(os.path.join(base, "status"), encoding="utf-8") as f:
                charging = f.read().strip().lower() in ("charging", "full")
        except (OSError, ValueError):
            continue
        return capacity, charging
    return None


def rounded_rect(cr, x: float, y: float, width: float, height: float, radius: float) -> None:
    """Trace a rounded rectangle; caller sets source and strokes/fills."""
    radius = min(radius, width / 2, height / 2)
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -0.5 * 3.14159265, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, 0.5 * 3.14159265)
    cr.arc(x + radius, y + height - radius, radius, 0.5 * 3.14159265, 3.14159265)
    cr.arc(x + radius, y + radius, radius, 3.14159265, 1.5 * 3.14159265)
    cr.close_path()


def paint_gauge(cr, window_width: int, reading: tuple[int, bool] | None) -> None:
    """Draw the gauge (and charging bolt) at its fixed top-right position."""
    x = window_width - GAUGE_RIGHT_MARGIN - GAUGE_WIDTH
    rounded_rect(cr, x, GAUGE_TOP, GAUGE_WIDTH, GAUGE_HEIGHT, GAUGE_RADIUS)
    cr.set_source_rgb(1, 1, 1)  # 2 px white border
    cr.set_line_width(GAUGE_BORDER)
    cr.stroke()
    fraction = (reading[0] / 100) if reading else 0.0
    fill_width = (GAUGE_WIDTH - 2 * GAUGE_BORDER) * max(0.0, min(1.0, fraction))
    if fill_width > 0:
        rounded_rect(
            cr,
            x + GAUGE_BORDER,
            GAUGE_TOP + GAUGE_BORDER,
            fill_width,
            GAUGE_HEIGHT - 2 * GAUGE_BORDER,
            max(1.0, GAUGE_RADIUS - GAUGE_BORDER),
        )
        cr.set_source_rgb(*GAUGE_FILL_RGB)
        cr.fill()
    if reading and reading[1]:
        bolt_x = x - 8 - BOLT_WIDTH
        bolt_y = GAUGE_TOP + (GAUGE_HEIGHT - BOLT_HEIGHT) // 2
        cr.move_to(bolt_x + BOLT_POINTS[0][0], bolt_y + BOLT_POINTS[0][1])
        for px, py in BOLT_POINTS[1:]:
            cr.line_to(bolt_x + px, bolt_y + py)
        cr.close_path()
        cr.set_source_rgb(*BOLT_RGB)
        cr.fill()


class BatteryMonitor:
    """sysfs polling: keeps the current reading and invalidates on change."""

    def __init__(self, invalidate, refresh_seconds: int = REFRESH_SECONDS):
        self.invalidate = invalidate
        self.refresh_seconds = refresh_seconds
        self.reading: tuple[int, bool] | None = None
        self.refresh()

    def refresh(self) -> bool:
        """Re-read sysfs and re-arm the timer; never raises."""
        self.reading = read_battery()
        self.invalidate()
        GLib.timeout_add_seconds(self.refresh_seconds, self.refresh)
        return False