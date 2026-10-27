"""Volume-button input: evdev at the boundary, injected event sources for tests.

The monitor never kills processes and never reads PID files; it only emits
recognized GestureActions to the callback provided by the application layer.
"""

import time
from collections.abc import Callable
from typing import Protocol

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from leo_kiosk.domain.gestures import GestureAction, GestureRecognizer  # noqa: E402

# linux-input event codes we accept; everything else is ignored upstream.
EV_KEY = 1
KEY_VOLUMEUP = 115
KEY_VOLUMEDOWN = 114

# A lone tap adjusts the volume only after the gesture window passed: every
# gesture needs its keys within max_gap (1.0 s default), so 1.1 s means the
# tap was alone. Gesture taps never adjust volume; the delay is the price.
VOLUME_TAP_DELAY = 1.1
VOLUME_STEP = 5


class EventSource(Protocol):
    """Injected seam: real sources wrap evdev devices; tests use fakes."""

    def fileno(self) -> int: ...

    def read_events(self) -> list[tuple[int, int, int]]: ...

    def close(self) -> None: ...


class EvdevEventSource:
    """Real device source; requires read permission on the evdev node."""

    def __init__(self, path: str) -> None:
        import evdev

        self.path = path
        self._device = evdev.InputDevice(path)

    def fileno(self) -> int:
        return self._device.fd

    def read_events(self) -> list[tuple[int, int, int]]:
        return [(event.type, event.code, event.value) for event in self._device.read()]

    def close(self) -> None:
        self._device.close()

    @classmethod
    def is_volume_source(cls, path: str) -> bool:
        import evdev

        try:
            device = evdev.InputDevice(path)
        except (OSError, PermissionError):
            return False
        try:
            # evdev 2.x InputDevice is NOT a context manager; close explicitly.
            keys = device.capabilities(verbose=False, absinfo=False).get(evdev.ecodes.EV_KEY, [])
            codes = (
                {key for key, _junk in keys} if keys and isinstance(keys[0], tuple) else set(keys)
            )
            return KEY_VOLUMEUP in codes and KEY_VOLUMEDOWN in codes
        except (OSError, ValueError):
            return False
        finally:
            device.close()


def discover_volume_sources() -> tuple[list[EvdevEventSource], list[str]]:
    """Enumerate /dev/input devices exposing the volume keys."""
    import evdev

    sources: list[EvdevEventSource] = []
    errors: list[str] = []
    try:
        paths = evdev.list_devices()
    except Exception as exc:  # noqa: BLE001 - any scan failure must not crash the kiosk
        return [], [f"device scan failed: {exc}"]
    for path in paths:
        try:
            if EvdevEventSource.is_volume_source(path):
                sources.append(EvdevEventSource(path))
        except (OSError, PermissionError) as exc:
            errors.append(f"{path}: {exc}")
    return sources, errors


def _wpctl_volume_step(code: int) -> None:
    """Adjust the default sink; fire-and-forget, failures stay silent."""
    import subprocess

    step = f"{VOLUME_STEP}%+" if code == KEY_VOLUMEUP else f"{VOLUME_STEP}%-"
    try:
        subprocess.Popen(
            ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", step],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass  # no pipewire/wpctl: the tap changes nothing, the kiosk keeps running


def _default_schedule(delay: float, fn: Callable[..., None], *args: int) -> object:
    def run() -> bool:
        fn(*args)
        return False  # one-shot source

    return GLib.timeout_add(int(delay * 1000), run)


def _default_cancel(handle: object) -> None:
    GLib.source_remove(handle)


class VolumeInputMonitor:
    """GLib-attached monitor; fakes without fileno are pumped manually in tests.

    Volume keys serve two masters: multi-key sequences are gestures, a lone
    tap is a volume step. A press schedules a volume change that fires only
    if no further key arrives within the gesture window (slightly over
    max_gap) and no gesture matched — so UDD/DU/DD stay volume-neutral and
    every other tap adjusts the default sink.
    """

    def __init__(
        self,
        sources: list[EventSource],
        on_action: Callable[[GestureAction], None],
        recognizer: GestureRecognizer | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_volume: Callable[[int], None] | None = None,
        volume_delay: float = VOLUME_TAP_DELAY,
        schedule=None,
        cancel=None,
    ) -> None:
        self.sources = [s for s in sources if s is not None]
        self.on_action = on_action
        self.recognizer = recognizer or GestureRecognizer(clock=clock)
        self._watch_ids: list[int] = []
        self.attached = False
        self._volume_runner = on_volume or _wpctl_volume_step
        self._volume_delay = volume_delay
        self._schedule = schedule or _default_schedule
        self._cancel = cancel or _default_cancel
        self._pending_volume: object | None = None

    def start(self) -> None:
        """Attach GLib watches for real (fileno-bearing) sources."""
        if self.attached:
            return
        for source in self.sources:
            try:
                fd = source.fileno()
            except (OSError, AttributeError):
                continue  # test fakes and closed devices are pumped manually
            watch_id = GLib.io_add_watch(
                fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_readable, source
            )
            self._watch_ids.append(watch_id)
        self.attached = True

    def stop(self) -> None:
        if not self.attached:
            return
        for watch_id in self._watch_ids:
            GLib.source_remove(watch_id)
        self._watch_ids.clear()
        self.attached = False

    def _on_readable(self, _fd, _condition, source):
        self.pump(source)
        return True  # keep the watch

    def pump(self, source: EventSource) -> None:
        """Drain one source and emit at most one action per recognized pattern."""
        try:
            events = source.read_events()
        except (OSError, BlockingIOError):
            return
        for event_type, code, value in events:
            if event_type != EV_KEY or value != 1:
                continue  # releases and autorepeats never act (the recognizer
                # ignores them too; a held button adjusts by repeated taps)
            action = self.recognizer.feed(code, value)
            if action is not None:
                self._cancel_pending_volume()
                self.on_action(action)
                return  # one action per drain; remaining taps start a new sequence
            self._schedule_volume(code)

    # --- lone-tap volume --------------------------------------------------
    def _schedule_volume(self, code: int) -> None:
        """A press may become a volume step if nothing follows it."""
        self._cancel_pending_volume()
        self._pending_volume = self._schedule(
            self._volume_delay, self._fire_volume, code
        )

    def _fire_volume(self, code: int) -> None:
        self._pending_volume = None
        self._volume_runner(code)

    def _cancel_pending_volume(self) -> None:
        if self._pending_volume is not None:
            self._cancel(self._pending_volume)
            self._pending_volume = None
