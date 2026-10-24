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
