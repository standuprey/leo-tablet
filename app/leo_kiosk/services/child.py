"""Child age: birthday validation, age math, and game age-range matching."""

import sqlite3
from datetime import date, datetime
from uuid import UUID

from leo_kiosk.domain.errors import StorageError, ValidationError
from leo_kiosk.storage.child import (
    ChildRepository,
    GamePlaytimeRepository,
    ScreenTimeRepository,
)
from leo_kiosk.storage.database import transaction

MAX_AGE = 17  # mirrors the game age-range bound (AgeRange 1-17)


def parse_birthday(
    day: int | None, month: int | None, year: int | None, today: date
) -> date:
    """Validate the birthday form fields into a real, past, plausible date."""
    if day is None or month is None or year is None:
        raise ValidationError("Pick the birthday day, month and year")
    try:
        birthday = date(year, month, day)
    except ValueError as exc:
        raise ValidationError("That is not a real date") from exc
    if birthday > today:
        raise ValidationError("The birthday cannot be in the future")
    if age_years(birthday, today) > MAX_AGE:
        raise ValidationError(f"The child cannot be older than {MAX_AGE}")
    return birthday


def age_years(birthday: date, today: date) -> int:
    """Completed years between birthday and today."""
    years = today.year - birthday.year
    if (today.month, today.day) < (birthday.month, birthday.day):
        years -= 1
    return years


def matches_age(age_min: int | None, age_max: int | None, age: int) -> bool:
    """A game is right for the age when the child's age fits its range.

    An unset bound is open-ended; both unset means 'no age information'.
    """
    if age_min is not None and age < age_min:
        return False
    if age_max is not None and age > age_max:
        return False
    return True


class ChildService:
    """Birthday + daily screen-time limit persistence for the My Child page."""

    def __init__(self, repository: ChildRepository) -> None:
        self._repository = repository

    def birthday(self) -> date | None:
        return self._repository.birthday()

    def set_birthday(self, birthday: date) -> None:
        with transaction(self._repository._connection):
            self._repository.set_birthday(birthday)

    def age(self, today: date) -> int | None:
        birthday = self._repository.birthday()
        return None if birthday is None else age_years(birthday, today)

    def screen_time_limit(self) -> int | None:
        return self._repository.screen_time_minutes()

    def set_screen_time(self, minutes: int | None) -> None:
        with transaction(self._repository._connection):
            self._repository.set_screen_time(minutes)


def _parse_screen_time(raw: str) -> int | None:
    """'' = no limit; otherwise an integer 0-600 minutes."""
    text = raw.strip()
    if not text:
        return None
    try:
        minutes = int(text)
    except ValueError as exc:
        raise ValidationError("Screen time must be a number of minutes") from exc
    if not 0 <= minutes <= 600:
        raise ValidationError("Screen time must be between 0 and 600 minutes")
    return minutes


class ScreenTimeService:
    """Used-seconds bookkeeping and the remaining/blocked computation.

    Usage accumulates per local day (the budget resets every day); the
    running app's elapsed time is recorded once, on its exit.
    """

    def __init__(
        self, limits: ChildRepository, usage: ScreenTimeRepository, per_game: GamePlaytimeRepository | None = None
    ) -> None:
        self._limits = limits
        self._usage = usage
        self._per_game = per_game

    def limit(self) -> int | None:
        return self._limits.screen_time_minutes()

    def set_limit(self, minutes: int | None) -> None:
        with transaction(self._limits._connection):
            self._limits.set_screen_time(minutes)

    def used_seconds(self, now: datetime) -> int:
        return self._usage.used_seconds(now.date().isoformat())

    def record(self, seconds: float, now: datetime, game_id: UUID | None = None) -> None:
        """Add one finished app's elapsed time to today's budget.

        With a game identity the same seconds are also attributed per game
        (the "most played" ranking); both rows share the caller's transaction.
        """
        if seconds <= 0:
            return
        whole = int(seconds + 0.5)
        if whole <= 0:
            return
        day = now.date().isoformat()
        with transaction(self._usage._connection):
            self._usage.add_seconds(day, whole)
            if game_id is not None:
                if not isinstance(game_id, UUID):
                    raise ValidationError("Playtime game identity must be a UUID")
                assert self._per_game is not None
                self._per_game.add_seconds(day, str(game_id), whole)

    def most_played(self, limit: int = 10) -> list[sqlite3.Row]:
        """Games ranked by all-time recorded seconds, most played first."""
        if self._per_game is None:
            raise StorageError("Per-game playtime is not available")
        return self._per_game.most_played(limit)

    def remaining_minutes(self, now: datetime) -> int | None:
        """Minutes left today; None when the parent set no limit."""
        limit = self.limit()
        if limit is None:
            return None
        used_minutes = -(-self.used_seconds(now) // 60)  # ceil
        return max(0, limit - used_minutes)

    def blocked(self, now: datetime) -> bool:
        remaining = self.remaining_minutes(now)
        return remaining is not None and remaining <= 0
