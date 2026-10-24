"""leopowerd: owns the Surface Go power button for Léo's kiosk.

The EC reports the button (Intel HID 5 button array) as an atomic
press+release with no hold information — see drivers/platform/x86/intel/hid.c
(sparse_keymap_report_event with autorelease). logind therefore cannot
implement press/hold behaviour for it; this daemon does instead:

  press while screen on    -> backlight off, arm the sleep timer
  press while screen off   -> backlight on, cancel the sleep timer
  press during a game      -> exit the game back to the home screen
  timer expiry (60 s)      -> suspend via logind
  resume from suspend      -> backlight on

Power off is a parent-mode action, never this button. Runs as root (systemd
unit): the input device and backlight sysfs need it, and root may suspend
without polkit interaction. Because it is root, a game kill is guarded: the
PID from .app-pid must belong to the kiosk user AND match a known tile
command, so a recycled PID can never be killed by mistake.
"""

import json
import os
import pwd
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import gi

gi.require_version("GLib", "2.0")
import evdev  # noqa: E402
from gi.repository import Gio, GLib  # noqa: E402

SLEEP_AFTER_OFF_SECONDS = 60
BUTTON_DEVICE_NAME = "Intel HID 5 button array"
BACKLIGHT_NAME = "intel_backlight"
KIOSK_USER = "leo"
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / ".app-pid"
TILES_FILE = HERE / "tiles.json"


def tile_commands(tiles_text: str) -> set[str]:
    """First argv token (basename) of every tile command in tiles.json."""
    commands: set[str] = set()
    try:
        data = json.loads(tiles_text)
    except ValueError:
        return commands
    for tile in data.get("tiles", []):
        cmd = tile.get("cmd") or []
        if cmd:
            commands.add(os.path.basename(str(cmd[0])))
    return commands


def status_uid(status_text: str) -> int | None:
    """Real UID from a /proc/<pid>/status Uid line."""
    for line in status_text.splitlines():
        if line.startswith("Uid:"):
            fields = line.split()
            if len(fields) >= 2:
                try:
                    return int(fields[1])
                except ValueError:
                    return None
    return None


def cmdline_allowed(cmdline_text: str, commands: set[str]) -> bool:
    """True when argv[0]'s basename is a known tile command."""
    argv0 = cmdline_text.split("\0")[0] if cmdline_text else ""
    return bool(argv0) and os.path.basename(argv0) in commands


def decide_press(screen_on: bool, game_pid: int | None) -> str:
    """What one power press means, given the current state."""
    if game_pid is not None:
        return "exit_game"
    return "blank" if screen_on else "unblank"


def _kiosk_uid() -> int | None:
    try:
        return pwd.getpwnam(KIOSK_USER).pw_uid
    except KeyError:
        return None


def find_backlight() -> Path:
    base = Path("/sys/class/backlight")
    preferred = base / BACKLIGHT_NAME
    if preferred.is_dir():
        return preferred
    for entry in sorted(base.iterdir()):
        if (entry / "brightness").exists():
            return entry
    raise RuntimeError("no backlight device found")


def find_button_device() -> "evdev.InputDevice[Any]":
    for path in evdev.list_devices():
        device = evdev.InputDevice(path)
        if BUTTON_DEVICE_NAME in device.name:
            return device
    raise RuntimeError(f"no input device named {BUTTON_DEVICE_NAME!r}")


class PowerDaemon:
    def __init__(self) -> None:
        self.backlight = find_backlight()
        self.max_brightness = self._read_int("max_brightness")
        self.saved_brightness = self.max_brightness
        current = self._read_int("brightness")
        self.screen_on = current > 0
        self.sleep_timer_id = 0
        self.device = find_button_device()
        os.set_blocking(self.device.fd, False)
        self.logind = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            None,
        )
        self.logind.connect("g-signal", self._on_logind_signal)
        watch = GLib.io_add_watch(
            self.device.fd, GLib.IOCondition.IN, self._on_button_readable
        )
        if watch == 0:
            raise RuntimeError("failed to watch the button device")
        if not self.screen_on:
            # e.g. restarted while the screen was dark: treat as screen-off.
            self._arm_sleep_timer()
        print(
            f"leopowerd: watching {self.device.path!r}, backlight {self.backlight}",
            file=sys.stderr,
            flush=True,
        )

    def _read_int(self, name: str) -> int:
        return int((self.backlight / name).read_text().strip())

    def _write_brightness(self, value: int) -> None:
        (self.backlight / "brightness").write_text(str(value))

    def _arm_sleep_timer(self) -> None:
        self.sleep_timer_id = GLib.timeout_add_seconds(
            SLEEP_AFTER_OFF_SECONDS, self._on_sleep_timer
        )

    def _cancel_sleep_timer(self) -> None:
        if self.sleep_timer_id:
            GLib.source_remove(self.sleep_timer_id)
            self.sleep_timer_id = 0

    def _on_sleep_timer(self) -> bool:
        self.sleep_timer_id = 0
        print("leopowerd: screen off long enough, suspending", file=sys.stderr, flush=True)
        # root bypasses polkit; do not wait — the call blocks until resume.
        subprocess.Popen(["systemctl", "suspend"])
        return False

    def blank(self) -> None:
        if self.screen_on:
            self.saved_brightness = max(self._read_int("brightness"), 1)
            self._write_brightness(0)
            self.screen_on = False
            self._arm_sleep_timer()
            print("leopowerd: screen off", file=sys.stderr, flush=True)

    def unblank(self) -> None:
        if not self.screen_on:
            self._write_brightness(self.saved_brightness)
            self.screen_on = True
            print("leopowerd: screen on", file=sys.stderr, flush=True)
        self._cancel_sleep_timer()

    def current_game_pid(self) -> int | None:
        """Running game's PID from .app-pid, or None.

        Because we are root, validate before ever acting on the PID: the
        process must belong to the kiosk user and match a known tile
        command, so a recycled PID can never be signalled.
        """
        try:
            pid = int(STATE_FILE.read_text().strip())
        except (OSError, ValueError):
            return None
        commands = tile_commands(TILES_FILE.read_text()) if TILES_FILE.exists() else set()
        try:
            status = Path(f"/proc/{pid}/status").read_text()
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            return None
        expected_uid = _kiosk_uid()
        if expected_uid is not None and status_uid(status) != expected_uid:
            return None
        if not cmdline_allowed(cmdline, commands):
            return None
        return pid

    def exit_game(self, pid: int) -> None:
        """Terminate the game's process group; the launcher brings back the tiles."""
        try:
            os.killpg(pid, signal.SIGTERM)
            print(f"leopowerd: SIGTERM to process group {pid}", file=sys.stderr, flush=True)
        except (ProcessLookupError, PermissionError) as exc:
            print(f"leopowerd: killpg {pid} failed: {exc}", file=sys.stderr, flush=True)

    def _on_button_readable(self, _fd: int, _condition: GLib.IOCondition) -> bool:
        try:
            for event in self.device.read():
                is_press = (
                    event.type == evdev.ecodes.EV_KEY
                    and event.code == evdev.ecodes.KEY_POWER
                    and event.value > 0
                )
                if not is_press:
                    continue
                # Down and up arrive atomically; act on the press only.
                game_pid = self.current_game_pid()
                if game_pid is not None and decide_press(self.screen_on, game_pid) == "exit_game":
                    self.exit_game(game_pid)
                    self.unblank()
                elif self.screen_on:
                    self.blank()
                else:
                    self.unblank()
        except BlockingIOError:
            pass
        return True

    def _on_logind_signal(
        self, _proxy: Gio.DBusProxy, _sender: str, signal: str, params: GLib.Variant
    ) -> None:
        if signal == "PrepareForSleep" and not params.unpack()[0]:
            # Resumed: restore the screen so the kiosk is visible again.
            self.unblank()


def main() -> int:
    try:
        PowerDaemon()
    except Exception as exc:  # noqa: BLE001 - a daemon must not crash-loop silently
        print(f"leopowerd: startup failed: {exc}", file=sys.stderr, flush=True)
        return 1
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
