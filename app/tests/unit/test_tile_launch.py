"""Tile-launch engine: the legacy launcher behavior, headless.

Ported from the removed ui/test_shell.py; the assertions are unchanged, only
the GTK window is replaced by recorded callbacks.
"""

import json
import os
import stat

import pytest

from leo_kiosk.services.tile_launch import TileLauncher


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


TILES = {
    "read": {"id": "read", "label": "ABC", "color": "#ff6b6b",
             "cmd": ["gcompris-qt"], "minutes": 25},
    "draw": {"id": "draw", "label": "Draw", "color": "#ffd43b",
             "cmd": ["missing-app"], "alt": ["true"], "minutes": 5},
}


@pytest.fixture
def engine(tmp_path):
    config = tmp_path / "tiles.json"
    config.write_text(
        json.dumps({"title": "LÉO", "tiles": list(TILES.values())},
                   ensure_ascii=False)
    )
    popen = RecordingPopen()
    player = Player()
    statuses, events = [], []
    engine = TileLauncher(
        state_path=str(tmp_path / ".app-pid"),
        voices_dir=str(tmp_path / "voices"),
        popen=popen,
        clock=lambda: 1000.0,
        player=player,
        call_later=lambda seconds, fn: (seconds, fn),
        on_status=statuses.append,
        on_enter=lambda: events.append("enter"),
        on_return=lambda: events.append("return"),
    )
    engine._statuses = statuses
    engine._events = events
    return engine, popen, player, tmp_path


def tile_by_id(_engine, tile_id):
    return TILES[tile_id]


def test_launch_spawns_with_its_own_session_and_records_pid(engine):
    engine, popen, _player, tmp_path = engine
    engine.launch(tile_by_id(engine, "read"))
    assert popen.calls and popen.calls[0] == ("gcompris-qt",)
    assert popen.start_new_session is True
    state = tmp_path / ".app-pid"
    assert state.read_text() == "70001"
    assert stat.S_IMODE(state.stat().st_mode) & 0o077 == 0
    assert engine._events == ["enter"]


def test_second_launch_while_running_is_ignored(engine):
    engine, popen, _player, _tmp = engine
    engine.launch(tile_by_id(engine, "read"))
    first = popen.calls
    engine.launch(tile_by_id(engine, "draw"))
    assert popen.calls == first


def test_fallback_command_is_tried_after_primary(engine):
    engine, popen, _player, _tmp = engine
    popen.fail = True
    engine.launch(tile_by_id(engine, "draw"))
    assert popen.calls[0] == ("missing-app",)
    popen.fail = False
    engine.launch(tile_by_id(engine, "draw"))
    assert ("true",) in popen.calls


def test_spawn_failure_shows_message_and_writes_no_state(engine):
    engine, popen, _player, tmp_path = engine
    popen.fail = True
    engine.launch(
        {"id": "x", "label": "X", "color": "#fff", "cmd": ["missing"],
         "alt": ["missing2"], "minutes": 5}
    )
    assert engine._statuses == ["Ask Papa to fix this one!"]
    assert not (tmp_path / ".app-pid").exists()
    assert engine._events == []  # window never hidden


def test_voice_file_is_preferred_over_tap_sound(engine):
    engine, _popen, player, tmp_path = engine
    (tmp_path / "voices").mkdir(exist_ok=True)
    (tmp_path / "voices" / "read.wav").write_bytes(b"RIFF")
    engine.launch(tile_by_id(engine, "read"))
    assert player.paths[-1].endswith("read.wav")


def test_launch_without_sound_is_silent_but_still_launches(engine):
    engine, popen, player, _tmp = engine
    engine.launch(tile_by_id(engine, "read"), play_sound=False)
    assert popen.calls == [("gcompris-qt",)]
    assert player.paths == []


def test_watch_with_finished_process_restores_home_and_removes_state(engine):
    engine, popen, _player, tmp_path = engine
    engine.launch(tile_by_id(engine, "read"))
    popen.returncode = 0
    engine._watch()
    assert engine._events == ["enter", "return"]
    assert not (tmp_path / ".app-pid").exists()
    assert engine.proc is None


def test_watch_after_deadline_sends_term_then_kill(engine, monkeypatch):
    engine, _popen, _player, _tmp = engine
    signals = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append(sig))
    engine.launch(tile_by_id(engine, "read"))
    engine.deadline = 999.0  # clock() == 1000 is past deadline
    engine._watch()
    assert signals == [15]  # SIGTERM first; KILL follows via force_kill
    engine.force_kill()
    assert signals == [15, 9]


