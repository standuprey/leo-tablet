"""Immutable playback context: historical records never authorize PID signaling."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from .catalog import CatalogItem
from .errors import ValidationError


class LaunchRole(StrEnum):
    CHILD_GAME = "child_game"
    CHILD_LEGACY = "child_legacy"
    REVIEW_TRIAL = "review_trial"


class LaunchPhase(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FINISHED = "finished"


class LaunchOutcome(StrEnum):
    EXITED = "exited"
    RETURN_GESTURE = "return_gesture"
    PARENT_REQUEST = "parent_request"
    TIMED_OUT = "timed_out"
    SPAWN_FAILED = "spawn_failed"
    CRASHED = "crashed"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class LaunchContext:
    role: LaunchRole
    game_id: UUID | None = None
    slot: int | None = None
    token: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.role, LaunchRole) or not isinstance(self.token, UUID):
            raise ValidationError("Launch role and ownership token must be explicit")
        if self.game_id is not None and not isinstance(self.game_id, UUID):
            raise ValidationError("Game identity must be a UUID")
        if self.role == LaunchRole.REVIEW_TRIAL:
            if self.game_id is None or self.slot is not None:
                raise ValidationError("Review trials require a game and no home position")
        elif type(self.slot) is not int or not 1 <= self.slot <= 9:
            raise ValidationError("Child playback requires a home position from 1 to 9")
        elif (self.role == LaunchRole.CHILD_GAME) != (self.game_id is not None):
            raise ValidationError("Only child game playback carries a game identity")


@dataclass(frozen=True)
class LaunchResult:
    context: LaunchContext
    outcome: LaunchOutcome
    started_at: datetime | None
    ended_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, LaunchOutcome):
            raise ValidationError("Launch outcome must be explicit")
        for timestamp in (self.started_at, self.ended_at):
            if timestamp is not None and timestamp.utcoffset() != timedelta(0):
                raise ValidationError("Launch history must use timezone-aware UTC timestamps")
        if self.started_at is not None and self.ended_at < self.started_at:
            raise ValidationError("A launch cannot end before it starts")


class SessionService(Protocol):
    def launch_game(self, item: CatalogItem, context: LaunchContext, minutes: int) -> UUID: ...

    def stop(self, token: UUID, outcome: LaunchOutcome) -> None: ...
