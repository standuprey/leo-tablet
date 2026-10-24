"""Token-owned trial sessions: spawn, stop, natural exit, profile cleanup.

Callbacks are token-checked; termination is TERM then bounded KILL. The
scheduler/watch hooks are injected so tests run without GLib or processes.
"""

import os
import signal
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.domain.sessions import LaunchOutcome, LaunchRole
from leo_kiosk.storage.database import transaction
from leo_kiosk.storage.sessions import SessionRepository

Scheduler = Callable[[int, Callable[[], None]], object]
Cancel = Callable[[object], None]
Watch = Callable[[object, Callable[[int, int], None]], object]
Finished = Callable[[UUID, UUID, LaunchOutcome], None]
Clock = Callable[[], datetime]


class ProcessHandle(Protocol):
    pid: int

    def poll(self) -> int | None: ...


class ProfileManager(Protocol):
    def new_trial_profile(self) -> Path: ...

    def cleanup_profile(self, profile: Path) -> None: ...


class TrialSessionService:
    KILL_GRACE_SECONDS = 3

    def __init__(
        self,
        repository: SessionRepository,
        popen: Callable[..., ProcessHandle],
        profiles: ProfileManager,
        call_later: Scheduler | None = None,
        cancel_later: Cancel | None = None,
        watch_process: Watch | None = None,
        on_finished: Finished | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._popen = popen
        self._profiles = profiles
        self._call_later: Scheduler = call_later or _noop_scheduler
        self._cancel_later: Cancel = cancel_later or _noop_cancel
        self._watch_process: Watch = watch_process or _noop_watch
        self.on_finished = on_finished
        self._clock = clock or (lambda: datetime.now(UTC))
        self._active: dict[UUID, _Session] = {}

    def start_trial(self, url: str, game_id: UUID) -> UUID:
        if self._active:
            raise ValidationError("A trial is already running")
        from leo_kiosk.adapters.firefox import build_firefox_command

        token = uuid4()
        profile = self._profiles.new_trial_profile()
        command = build_firefox_command("firefox", profile, url)
        try:
            process = self._popen(
                command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._profiles.cleanup_profile(profile)
            self._record_history(token, game_id)
            self._record_finish(token, LaunchOutcome.SPAWN_FAILED, str(exc))
            raise ValidationError("Cannot start the game browser") from exc
        session = _Session(token, game_id, process, profile)
        self._active[token] = session
        self._record_history(token, game_id)
        self._watch_process(process, lambda _pid, _code: self._on_exit(token))
        return token

    def stop(self, token: UUID, outcome: LaunchOutcome) -> None:
        session = self._active.get(token)
        if session is None:
            return
        self._signal_group(session, signal.SIGTERM)
        session.pending_outcome = outcome  # wins over the exit-code heuristic
        timeout_id = self._call_later(self.KILL_GRACE_SECONDS, lambda: self._force_kill(token))
        session.kill_timeout_id = timeout_id

    def _force_kill(self, token: UUID) -> None:
        session = self._active.get(token)
        if session is not None:
            self._signal_group(session, signal.SIGKILL)

    def _on_exit(self, token: UUID) -> None:
        session = self._active.pop(token, None)
        if session is None:
            return  # already finished via stop(); stop's own path finishes it
        self._cancel_later(session.kill_timeout_id)
        outcome = session.pending_outcome or (
            LaunchOutcome.CRASHED if (session.process.poll() or 0) != 0 else LaunchOutcome.EXITED
        )
        self._finish(token, session, outcome)

    def finish_with_outcome(self, token: UUID, outcome: LaunchOutcome) -> None:
        """Stop-driven completion: record outcome and clean up immediately."""
        session = self._active.pop(token, None)
        if session is None:
            return
        self._cancel_later(session.kill_timeout_id)
        self._finish(token, session, outcome)

    def _record_history(self, token: UUID, game_id: UUID) -> None:
        with transaction(self._repository.connection):
            self._repository.start_session(
                token, game_id, None, LaunchRole.REVIEW_TRIAL.value, self._clock()
            )

    def _record_finish(
        self, token: UUID, outcome: LaunchOutcome, failure_reason: str | None = None
    ) -> None:
        with transaction(self._repository.connection):
            self._repository.finish_session(token, self._clock(), outcome.value, failure_reason)

    def _finish(self, token: UUID, session: "_Session", outcome: LaunchOutcome) -> None:
        self._record_finish(token, outcome)
        self._profiles.cleanup_profile(session.profile)
        if self.on_finished is not None:
            self.on_finished(token, session.game_id, outcome)

    def _signal_group(self, session: "_Session", sig: int) -> None:
        try:
            os.killpg(session.process.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    @property
    def active_tokens(self) -> tuple[UUID, ...]:
        return tuple(self._active)


@dataclass
class _Session:
    token: UUID
    game_id: UUID
    process: ProcessHandle
    profile: Path
    kill_timeout_id: object = None
    pending_outcome: LaunchOutcome | None = None


def _noop_scheduler(_seconds: int, _fn: Callable[[], None]) -> None:
    return None


def _noop_cancel(_handle: object) -> None:
    return None


def _noop_watch(_process: object, _callback: Callable[[int, int], None]) -> None:
    return None
