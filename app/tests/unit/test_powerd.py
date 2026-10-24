"""Unit tests for the leopowerd decision logic and kill guards.

leopowerd runs as root and kills process groups, so its guards are pure
functions tested here; the GLib/evdev wiring needs the real device and is
covered by the on-device checklist instead.
"""

import powerd


def test_tile_commands_extracts_first_token_basename() -> None:
    text = """
    {"tiles": [
      {"id": "a", "cmd": ["gcompris-qt"]},
      {"id": "b", "cmd": ["firefox", "--kiosk", "file://x"]},
      {"id": "c", "cmd": []}
    ]}
    """
    assert powerd.tile_commands(text) == {"gcompris-qt", "firefox"}


def test_tile_commands_survives_invalid_json() -> None:
    assert powerd.tile_commands("not json") == set()


def test_status_uid_parses_real_uid_field() -> None:
    status = "Name:\tvlc\nUid:\t1001\t1001\t1001\t1001\nGroups:\t998\n"
    assert powerd.status_uid(status) == 1001


def test_status_uid_returns_none_without_uid_line() -> None:
    assert powerd.status_uid("Name:\tx\n") is None
    assert powerd.status_uid("Uid:\tbroken\n") is None


def test_cmdline_allowed_matches_known_tile_command() -> None:
    assert powerd.cmdline_allowed("gcompris-qt\0--fullscreen\0", {"gcompris-qt"})
    assert powerd.cmdline_allowed("/usr/bin/vlc\0", {"vlc"})


def test_cmdline_allowed_rejects_unknown_or_empty() -> None:
    assert not powerd.cmdline_allowed("systemd\0--user\0", {"vlc"})
    assert not powerd.cmdline_allowed("", {"vlc"})
    assert not powerd.cmdline_allowed("gcompris-qt\0", set())


def test_press_decision_table() -> None:
    assert powerd.decide_press(True, None) == "blank"
    assert powerd.decide_press(False, None) == "unblank"
    assert powerd.decide_press(True, 4711) == "exit_game"
    assert powerd.decide_press(False, 4711) == "exit_game"
