"""Token-owned review trials shown in the launcher's own view.

There is no browser process anymore: the controller navigates the single
WebKitGTK view to the game URL and the service owns the trial's lifecycle —
history rows, gesture-driven outcomes and a safety deadline. The deadline
(default 30 minutes, architecture §7) ends an abandoned trial as timed_out;
gestures end it with their own outcome. Callbacks are token-checked;
schedulers are injected so tests run without GLib.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.domain.sessions import LaunchOutcome, LaunchRole
from leo_kiosk.storage.database import transaction
from leo_kiosk.storage.sessions import SessionRepository

Scheduler = Callable[[int, Callable[[], None]], object]
Cancel = Callable[[object], None]
Finished = Callable[[UUID, UUID, LaunchOutcome], None]
Clock = Callable[[], datetime]


class TrialSessionService:
    TRIAL_TIMEOUT_SECONDS = 30 * 60

    def __init__(
        self,
        repository: SessionRepository,
        call_later: Scheduler | None = None,
        cancel_later: Cancel | None = None,
        on_finished: Finished | None = None,
        clock: Clock | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._repository = repository
        self._call_later: Scheduler = call_later or _noop_scheduler
        self._cancel_later: Cancel = cancel_later or _noop_cancel
        self.on_finished = on_finished
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timeout = timeout_seconds if timeout_seconds is not None else self.TRIAL_TIMEOUT_SECONDS
        self._active: dict[UUID, _Session] = {}

    def start_trial(self, url: str, game_id: UUID) -> UUID:
        """A parent-driven review trial; 30-minute safety deadline."""
        return self._start(
            url, game_id, slot=None, role=LaunchRole.REVIEW_TRIAL,
            timeout_seconds=self._timeout,
        )

    def start_child_game(
        self, url: str, game_id: UUID, slot: int, minutes: int
    ) -> UUID:
        """A child tap on a placed home game: role child_game (slot recorded),

        capped by the tile's per-session minutes, not the review deadline.
        """
        if type(minutes) is not int or not 1 <= minutes <= 240:
            raise ValidationError("Child session minutes must be 1-240")
        return self._start(
            url, game_id, slot=slot, role=LaunchRole.CHILD_GAME,
            timeout_seconds=minutes * 60,
        )

    def _start(
        self,
        url: str,
        game_id: UUID,
        *,
        slot: int | None,
        role: LaunchRole,
        timeout_seconds: int,
    ) -> UUID:
        if self._active:
            raise ValidationError("A trial is already running")
        token = uuid4()
        session = _Session(token, game_id)
        self._active[token] = session
        self._record_history(token, game_id, slot, role)
        session.timeout_id = self._call_later(
            timeout_seconds, lambda: self._on_deadline(token)
        )
        return token

    def stop(self, token: UUID, outcome: LaunchOutcome) -> None:
        """Gesture-driven end: record the outcome and finish immediately."""
        session = self._active.pop(token, None)
        if session is None:
            return
        self._cancel_later(session.timeout_id)
        self._finish(token, session, outcome)

    def _on_deadline(self, token: UUID) -> None:
        session = self._active.pop(token, None)
        if session is None:
            return
        self._finish(token, session, LaunchOutcome.TIMED_OUT)

    def _record_history(
        self, token: UUID, game_id: UUID, slot: int | None, role: LaunchRole
    ) -> None:
        with transaction(self._repository.connection):
            self._repository.start_session(
                token, game_id, slot, role.value, self._clock()
            )

    def _finish(self, token: UUID, session: "_Session", outcome: LaunchOutcome) -> None:
        with transaction(self._repository.connection):
            self._repository.finish_session(token, self._clock(), outcome.value, None)
        if self.on_finished is not None:
            self.on_finished(token, session.game_id, outcome)

    @property
    def active_tokens(self) -> tuple[UUID, ...]:
        return tuple(self._active)


@dataclass
class _Session:
    token: UUID
    game_id: UUID
    timeout_id: object = None


def _noop_scheduler(_seconds: int, _fn: Callable[[], None]) -> None:
    return None


def _noop_cancel(_handle: object) -> None:
    return None
