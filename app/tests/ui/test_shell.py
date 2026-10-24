"""Extracted shell behavior; runs wherever a GTK display is available."""

import json
import os
import stat

import pytest

from leo_kiosk.ui.window import LauncherWindow


class RecordingPopen:
    def __init__(self, pid=70001, fail=False):
        self.pid = pid
        self.fail = fail
        self.calls = []
        self.start_new_session = None
        self.returncode = None

    def __call__(self, cmd, start_new_session=False, stdout=None, stderr=None):
        self.calls.append(tuple(cmd))
        self.start_new_session = start_new_session
        if self.fail:
            raise OSError("executable missing")
        return self

    def poll(self):
        return self.returncode


class Player:
    def __init__(self):
        self.paths = []

    def __call__(self, path):
        self.paths.append(path)


@pytest.fixture
def shell(tmp_path):
    config = tmp_path / "tiles.json"
    config.write_text(
        json.dumps(
            {
                "title": "LÉO",
                "columns": 3,
                "tiles": [
                    {
                        "id": "read",
                        "label": "ABC",
                        "color": "#ff6b6b",
                        "cmd": ["gcompris-qt"],
                        "minutes": 25,
                    },
                    {
                        "id": "draw",
                        "label": "Draw",
                        "color": "#ffd43b",
                        "cmd": ["missing-app"],
                        "alt": ["true"],
                        "minutes": 5,
                    },
                ],
            },
            ensure_ascii=False,
        )
    )
    popen = RecordingPopen()
    player = Player()
    window = LauncherWindow(
        config,
        tmp_path / ".app-pid",
        tmp_path / "voices",
        popen=popen,
        clock=lambda: 1000.0,
        player=player,
        on_corner_exit=lambda: None,
    )
    yield window, popen, player, tmp_path
    window.win.destroy()


def tile_by_label(shell, label):
    window = shell[0]
    return next(t for t in window.cfg["tiles"] if t["label"] == label)


@pytest.mark.display
def test_build_preserves_labels_colors_and_title(shell):
    window = shell[0]
    assert window.cfg["title"] == "LÉO"
    assert [t["label"] for t in window.cfg["tiles"]] == ["ABC", "Draw"]


@pytest.mark.display
def test_launch_spawns_with_its_own_session_and_records_pid(shell):
    window, popen, _player, tmp_path = shell
    window.launch(tile_by_label(shell, "ABC"))
    assert popen.calls and popen.calls[0] == ("gcompris-qt",)
    assert popen.start_new_session is True
    state = tmp_path / ".app-pid"
    assert state.read_text() == "70001"
    assert stat.S_IMODE(state.stat().st_mode) & 0o077 == 0


@pytest.mark.display
def test_second_launch_while_running_is_ignored(shell):
    window, popen, _player, _tmp = shell
    window.launch(tile_by_label(shell, "ABC"))
    first = popen.calls
    window.launch(tile_by_label(shell, "Draw"))
    assert popen.calls == first


@pytest.mark.display
def test_fallback_command_is_tried_after_primary(shell):
    window, popen, _player, _tmp = shell
    popen.fail = True
    window.launch(tile_by_label(shell, "Draw"))
    assert popen.calls[0] == ("missing-app",)
    popen.fail = False
    window.launch(tile_by_label(shell, "Draw"))
    assert ("true",) in popen.calls


@pytest.mark.display
def test_spawn_failure_shows_message_and_writes_no_state(shell):
    window, popen, _player, tmp_path = shell
    popen.fail = True
    window.launch(
        {
            "id": "x",
            "label": "X",
            "color": "#fff",
            "cmd": ["missing"],
            "alt": ["missing2"],
            "minutes": 5,
        }
    )
    assert window.status.get_text() == "Ask Papa to fix this one!"
    assert not (tmp_path / ".app-pid").exists()


@pytest.mark.display
def test_voice_file_is_preferred_over_tap_sound(shell, tmp_path):
    window, _popen, player, tmp_path = shell
    (tmp_path / "voices").mkdir(exist_ok=True)
    (tmp_path / "voices" / "read.wav").write_bytes(b"RIFF")
    window.launch(tile_by_label(shell, "ABC"))
    assert player.paths[-1].endswith("read.wav")


@pytest.mark.display
def test_watch_with_finished_process_restores_home_and_removes_state(shell):
    window, popen, player, tmp_path = shell
    window.launch(tile_by_label(shell, "ABC"))
    popen.returncode = 0
    assert window.watch() is False
    assert not (tmp_path / ".app-pid").exists()


@pytest.mark.display
def test_watch_after_deadline_sends_term_then_kill(shell, monkeypatch):
    window, popen, _player, _tmp = shell
    signals = []
    monkeypatch.setattr(
        os, "killpg", lambda pid, sig: signals.append(sig)
    )  # records both TERM and KILL for the fake pid
    window.launch(tile_by_label(shell, "ABC"))
    window.deadline = 999.0  # clock() == 1000 is past deadline
    assert window.watch() is False
    assert signals == [15]  # SIGTERM first; KILL follows via force_kill
    window.force_kill()
    assert signals == [15, 9]


@pytest.mark.display
def test_five_corner_taps_invoke_exit_hook(shell):
    window, *_rest = shell
    taps = {"n": 0}
    window.on_corner_exit = lambda: taps.__setitem__("n", taps["n"] + 1)
    for _ in range(5):
        window.on_corner(None)
    assert taps["n"] == 1


@pytest.mark.display
def test_corner_taps_expire_after_four_seconds(shell, fake_clock):
    window, *_rest = shell
    window.clock = fake_clock
    taps = {"n": 0}
    window.on_corner_exit = lambda: taps.__setitem__("n", taps["n"] + 1)
    for _ in range(4):
        window.on_corner(None)
    fake_clock.value += 5  # all four taps are now outside the 4 s window
    window.on_corner(None)
    assert taps["n"] == 0
