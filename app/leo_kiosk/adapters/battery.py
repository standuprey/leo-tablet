"""Battery reading from sysfs, for the web UI's /child-state endpoint.

Moved from ui/battery.py; the cairo gauge painting died with the GTK home
screen — the web UI draws its own gauge from the polled reading.
"""

import os

POWER_SUPPLY = "/sys/class/power_supply"


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
