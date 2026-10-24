"""Frozen review-next queue: order captured at activation, never reordered."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from uuid import UUID

from .errors import ValidationError


def _never(_id: UUID) -> bool:
    return False


@dataclass(frozen=True)
class ReviewQueue:
    """Snapshot of displayed eligible IDs; widgets must not re-derive order."""

    ids: tuple[UUID, ...] = field(default_factory=tuple)
    position: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.ids, tuple) or not all(isinstance(i, UUID) for i in self.ids):
            raise ValidationError("Queue requires a tuple of UUIDs")
        if type(self.position) is not int or not 0 <= self.position <= len(self.ids):
            raise ValidationError("Queue position out of range")

    @classmethod
    def from_ids(cls, ids: Iterable[UUID]) -> "ReviewQueue":
        return cls(tuple(ids))

    @property
    def exhausted(self) -> bool:
        return self.position >= len(self.ids)

    def current(self) -> UUID | None:
        return None if self.exhausted else self.ids[self.position]

    def advance(self) -> "ReviewQueue":
        if self.exhausted:
            return self
        return ReviewQueue(self.ids, self.position + 1)

    def next_id(self, skip: Callable[[UUID], bool] = _never) -> UUID | None:
        """First unskipped ID at or after the cursor; never wraps, never reorders."""
        index = self.position
        while index < len(self.ids):
            candidate = self.ids[index]
            if not skip(candidate):
                return candidate
            index += 1
        return None

    def advance_past(self, game_id: UUID) -> "ReviewQueue":
        """Move the cursor past the given ID (its review is being saved)."""
        for index in range(self.position, len(self.ids)):
            if self.ids[index] == game_id:
                return ReviewQueue(self.ids, index + 1)
        return self
