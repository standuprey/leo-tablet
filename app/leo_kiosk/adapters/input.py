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


class VolumeInputMonitor:
    """GLib-attached monitor; fakes without fileno are pumped manually in tests."""

    def __init__(
        self,
        sources: list[EventSource],
        on_action: Callable[[GestureAction], None],
        recognizer: GestureRecognizer | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sources = [s for s in sources if s is not None]
        self.on_action = on_action
        self.recognizer = recognizer or GestureRecognizer(clock=clock)
        self._watch_ids: list[int] = []
        self.attached = False

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
            if event_type != EV_KEY:
                continue
            action = self.recognizer.feed(code, value)
            if action is not None:
                self.on_action(action)
                return  # one action per drain; remaining taps start a new sequence
