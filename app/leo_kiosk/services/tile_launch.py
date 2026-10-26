"""Headless tile-launch engine, extracted from the legacy launcher window.

Behavior preserved from ``ui/window.py`` without change: tap voice or sound,
primary command with optional ``alt`` fallback, ``file://~`` expansion, one
app at a time, ``.app-pid`` ownership, deadline TERM then bounded KILL,
status messages. The GTK window is replaced by injected callbacks so the web
UI drives the same contract; the evdev watchers (backwatch, powerd) see the
same process-group and state-file semantics as before.
"""

import os
import signal
import subprocess
import sys
from collections.abc import Callable
from typing import Protocol, cast

TAP_SOUND = "/usr/share/sounds/freedesktop/stereo/message.oga"
POLL_SECONDS = 0.5
KILL_GRACE_SECONDS = 3
VOICE_EXTENSIONS = (".wav", ".ogg", ".oga", ".mp3")
CORNER_WINDOW_SECONDS = 4
CORNER_TAPS_TO_EXIT = 5


class Popen(Protocol):
    def __call__(  # noqa: D102 - shape mirrors subprocess.Popen's use here
        self,
        cmd: list[str],
        start_new_session: bool = ...,
        stdout: int = ...,
        stderr: int = ...,
    ) -> "ProcessHandle": ...


def play(path: str | None) -> None:
    """Best-effort sound playback; missing files are silently skipped."""
    if path is None or not os.path.exists(path):
        return
    try:
        subprocess.Popen(
            ["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError:
        pass


class ProcessHandle(Protocol):
    pid: int

    def poll(self) -> int | None: ...


class TileLauncher:
    """Launches tile commands and owns the running process end to end."""

    def __init__(
        self,
        state_path: str,
        voices_dir: str,
        popen: Popen,
        clock: Callable[[], float],
        player: Callable[[str | None], None],
        call_later: Callable[[float, Callable[[], None]], object],
        on_status: Callable[[str], None],
        on_enter: Callable[[], None],
        on_return: Callable[[], None],
        on_corner_exit: Callable[[], None],
    ) -> None:
        self.state_path = state_path
        self.voices_dir = voices_dir
        self.popen = popen
        self.clock = clock
        self.player = player
        self.call_later = call_later
        self.on_status = on_status
        self.on_enter = on_enter
        self.on_return = on_return
        self.on_corner_exit = on_corner_exit
        self.proc: ProcessHandle | None = None
        self.deadline = 0.0
        self.corner_taps: list[float] = []

    # --- launching -------------------------------------------------------
    def launch(self, tile: dict[str, object], play_sound: bool = True) -> None:
        """Launch one tile's command; ignored while an app is already running.

        ``play_sound=False`` reproduces the legacy Videos-screen behavior,
        which played no sound on tile taps.
        """
        if self.proc is not None and self.proc.poll() is None:
            return
        tile_id = str(tile.get("id", ""))
        if play_sound:
            self.player(self._voice(tile_id) or TAP_SOUND)

        home = os.path.expanduser("~")
        raws = [cast("list[list[str]]", tile["cmd"])]
        if tile.get("alt"):
            raws.append(cast("list[list[str]]", tile["alt"]))
        proc = None
        for raw in raws:
            cmd = [
                os.path.expanduser(str(a)).replace("file://~", "file://" + home)
                for a in raw
            ]
            try:
                proc = self.popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                break
            except OSError:
                continue
        if proc is None:
            print(f"launch failed for {raws}", file=sys.stderr, flush=True)
            self.on_status("Ask Papa to fix this one!")
            return
        self.proc = proc
        minutes = cast("int | str", tile.get("minutes", 20))
        self.deadline = self.clock() + float(minutes) * 60
        self.on_enter()
        self._write_state_file()
        self.call_later(POLL_SECONDS, self._watch)

    def _voice(self, tile_id: str) -> str | None:
        for ext in VOICE_EXTENSIONS:
            path = os.path.join(self.voices_dir, tile_id + ext)
            if os.path.exists(path):
                return path
        return None

    def _write_state_file(self) -> None:
        if self.proc is None:
            return
        try:
            fd = os.open(self.state_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(str(self.proc.pid))
        except OSError:
            pass

    # --- watching --------------------------------------------------------
    def _watch(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is not None:
            self.back_home()
            return
        if self.clock() > self.deadline:
            self.kill_group(signal.SIGTERM)
            self.call_later(KILL_GRACE_SECONDS, self.force_kill)
            return
        self.call_later(POLL_SECONDS, self._watch)

    def kill_group(self, sig: int) -> None:
        if self.proc is None:
            return
        try:
            os.killpg(self.proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def force_kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.kill_group(signal.SIGKILL)
        self.back_home()

    def back_home(self) -> None:
        self.on_return()
        try:
            os.remove(self.state_path)
        except OSError:
            pass
        self.proc = None
        self.player(TAP_SOUND)

    # --- parent corner ---------------------------------------------------
    def corner_tap(self) -> None:
        """Five taps within the window invoke the exit hook (kiosk escape)."""
        now = self.clock()
        self.corner_taps = [
            t for t in self.corner_taps if now - t < CORNER_WINDOW_SECONDS
        ] + [now]
        if len(self.corner_taps) >= CORNER_TAPS_TO_EXIT:
            self.corner_taps = []
            self.on_corner_exit()
