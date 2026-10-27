"""Input monitor: fake sources feed raw events; recognizer emits actions."""

import os
import struct

import pytest

from leo_kiosk.adapters.input import EV_KEY, VolumeInputMonitor
from leo_kiosk.domain.gestures import (
    DEFAULT_PATTERNS,
    REVIEW_TRIAL_PATTERNS,
    GestureAction,
    GestureRecognizer,
)

UP, DOWN = 115, 114  # KEY_VOLUMEUP / KEY_VOLUMEDOWN


class FakeSource:
    """Synthetic evdev source; read_events pops queued events."""

    def __init__(self):
        self.queued: list[tuple[int, int, int]] = []
        self.closed = False

    def fileno(self):
        return -1  # no real fd: monitor.start() skips it, tests pump manually

    def read_events(self):
        events, self.queued = self.queued, []
        return events

    def close(self):
        self.closed = True

    def press(self, code):
        self.queued.append((EV_KEY, code, 1))


@pytest.fixture
def monitor():
    actions = []
    source = FakeSource()
    recognizer = GestureRecognizer(
        clock=lambda: 0,
        config=__import__("leo_kiosk.domain.gestures", fromlist=["GestureConfig"]).GestureConfig(
            cooldown=0
        ),
    )
    m = VolumeInputMonitor([source], actions.append, recognizer=recognizer)
    return m, source, actions


def test_udd_emits_enter_parent_once(monitor):
    m, source, actions = monitor
    for code in (UP, DOWN, DOWN):
        source.press(code)
        m.pump(source)
    assert actions == [GestureAction.ENTER_PARENT]


def test_du_does_not_match_default_patterns(monitor):
    m, source, actions = monitor
    source.press(DOWN)
    m.pump(source)
    source.press(UP)
    m.pump(source)
    assert actions == []


def test_review_trial_patterns_enable_short_return(monitor):
    m, source, actions = monitor
    m.recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
    source.press(DOWN)
    m.pump(source)
    source.press(UP)
    m.pump(source)
    assert actions == [GestureAction.RETURN]


def test_repeats_releases_and_other_keys_are_ignored(monitor):
    m, source, actions = monitor
    for event in [(EV_KEY, UP, 0), (EV_KEY, DOWN, 2), (2, 42, 1), (EV_KEY, 42, 1)]:
        source.queued = [event]
        m.pump(source)
    source.press(UP)
    m.pump(source)
    source.press(DOWN)
    m.pump(source)
    source.press(DOWN)
    m.pump(source)
    assert actions == [GestureAction.ENTER_PARENT]


def test_one_action_per_drain(monitor):
    m, source, actions = monitor
    for code in (UP, DOWN, DOWN):
        source.press(code)
    m.pump(source)  # all three events drained in one batch
    assert actions == [GestureAction.ENTER_PARENT]


def test_read_failure_is_swallowed(monitor):
    class Broken(FakeSource):
        def read_events(self):
            raise BlockingIOError

    broken = Broken()
    monitor[0].pump(broken)  # no crash, no action
    assert monitor[2] == []


def test_start_skips_sources_without_fileno_and_stop_is_idempotent(monitor):
    m, _source, _actions = monitor
    m.start()  # fake source has no usable fd; nothing to attach
    m.stop()
    m.stop()
    assert not m.attached


def test_real_glib_watch_on_a_pipe(fake_clock):
    """End-to-end through GLib: write raw input_event bytes into a pipe."""
    from gi.repository import GLib

    actions = []
    read_fd, write_fd = os.pipe()
    recognizer = GestureRecognizer(clock=fake_clock)
    monitor = VolumeInputMonitor([], actions.append, recognizer=recognizer)

    class PipeSource:
        def fileno(self):
            return read_fd

        def read_events(self):
            try:
                data = os.read(read_fd, 24 * 8)
            except BlockingIOError:
                return []
            out = []
            for i in range(len(data) // 24):
                _, _, etype, code, value = struct.unpack("qqhhi", data[i * 24 : (i + 1) * 24])
                out.append((etype, code, value))
            return out

        def close(self):
            os.close(read_fd)

    os.set_blocking(read_fd, False)
    monitor.sources = [PipeSource()]
    monitor.start()
    assert monitor.attached
    for code in (UP, DOWN, DOWN):
        os.write(write_fd, struct.pack("qqhhi", 0, 0, EV_KEY, code, 1))
    # Pump the GLib source explicitly (no main loop in tests).
    while GLib.MainContext.default().iteration(False):
        pass
    # one action per pump; drain again for remaining events
    monitor.pump(monitor.sources[0])
    assert actions == [GestureAction.ENTER_PARENT]
    monitor.stop()
    assert not monitor.attached
    os.close(write_fd)


def test_default_pattern_set_unchanged_for_documentation():
    assert DEFAULT_PATTERNS[0][0][0] == UP  # UDD starts with UP


def test_real_device_enumeration_has_no_context_manager_regression():
    """evdev 2.x InputDevice is not a context manager; the probe must close
    devices explicitly. Runs only where /dev/input is readable."""
    import glob
    import os

    import pytest

    pytest.importorskip("evdev")
    devices = sorted(glob.glob("/dev/input/event*"))
    if not devices or not os.access(devices[0], os.R_OK):
        pytest.skip("no readable /dev/input devices")
    from leo_kiosk.adapters.input import EvdevEventSource, discover_volume_sources

    sources, errors = discover_volume_sources()
    assert errors == []
    for source in sources:
        assert source.path.startswith("/dev/input/event")
    for path in devices:  # every device must probe without raising
        EvdevEventSource.is_volume_source(path)


# --- lone-tap volume control -------------------------------------------------
class VolumeHarness:
    """Volume decisions with a manual scheduler that honours cancellation."""

    def __init__(self, monitor):
        self.monitor = monitor
        self.fired = []
        self.scheduled = []
        self.actions = []
        self.pending = {}
        monitor.on_action = self.actions.append
        monitor._volume_runner = lambda code: self.fired.append(code)

        def schedule(delay, fn, *args):
            handle = ("h", len(self.scheduled))
            self.scheduled.append((delay, fn, args))
            self.pending[handle] = (fn, args)
            return handle

        def cancel(handle):
            self.scheduled.append(("cancelled", handle))
            self.pending.pop(handle, None)

        monitor._schedule = schedule
        monitor._cancel = cancel

    def fire_everything_still_pending(self):
        for fn, args in list(self.pending.values()):
            fn(*args)


def _pump_press(monitor, code):
    class Src:
        def read_events(self):
            return [(EV_KEY, code, 1)]

        def close(self):
            pass

    monitor.pump(Src())


def _volume_monitor(**kwargs):
    from leo_kiosk.adapters.input import VolumeInputMonitor

    return VolumeInputMonitor([FakeSource()], lambda _a: None, **kwargs)


def test_lone_tap_schedules_a_volume_step_after_the_gesture_window():
    monitor = _volume_monitor()
    harness = VolumeHarness(monitor)
    _pump_press(monitor, UP)  # UP alone: nothing on the child home
    assert harness.fired == []
    # the tap waits out the gesture window: 1.1s, just over max_gap
    assert harness.scheduled[0][0] == 1.1
    assert harness.scheduled[0][2] == (UP,)
    _delay, fn, (code,) = harness.scheduled[0]
    fn(code)  # time passes, nothing else pressed
    assert harness.fired == [UP]


def test_down_tap_also_fires_volume_down():
    monitor = _volume_monitor()
    harness = VolumeHarness(monitor)
    _pump_press(monitor, DOWN)
    _delay, fn, (code,) = harness.scheduled[0]
    fn(code)
    assert harness.fired == [DOWN]


def test_gesture_taps_never_fire_volume():
    from leo_kiosk.domain.gestures import GestureConfig, GestureRecognizer

    monitor = _volume_monitor(
        recognizer=GestureRecognizer(clock=lambda: 0, config=GestureConfig(cooldown=0))
    )
    harness = VolumeHarness(monitor)
    # Up,Down,Down = parent entry: three presses, one action, no volume
    for code in (UP, DOWN, DOWN):
        _pump_press(monitor, code)
    assert harness.actions != []  # the gesture fired
    cancels = [c for c in harness.scheduled if c[0] == "cancelled"]
    assert len(cancels) >= 2  # later presses cancel earlier pendings
    harness.fire_everything_still_pending()
    assert harness.fired == []  # the gesture consumed all three taps


def test_return_gesture_volume_neutral_and_post_gesture_tap_adjusts():
    from leo_kiosk.domain.gestures import (
        PARENT_SURFACE_PATTERNS,
        GestureConfig,
        GestureRecognizer,
    )

    monitor = _volume_monitor(
        recognizer=GestureRecognizer(
            clock=lambda: 0,
            config=GestureConfig(cooldown=0),
            patterns=PARENT_SURFACE_PATTERNS,  # DU is a return here
        )
    )
    harness = VolumeHarness(monitor)
    _pump_press(monitor, DOWN)  # Down..
    _pump_press(monitor, UP)  # ..Up: return gesture
    harness.fire_everything_still_pending()
    assert harness.actions != []
    assert harness.fired == []  # both taps belonged to the gesture

    # a tap after the gesture (cooldown passed) is lone again: volume fires
    _pump_press(monitor, DOWN)
    _delay, fn, (code,) = harness.scheduled[-1]
    fn(code)
    assert harness.fired == [DOWN]
