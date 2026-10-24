"""Review/home values and UI-facing interfaces; no persistence or GTK side effects."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .catalog import CatalogItem
from .errors import ValidationError


class ReviewStatus(StrEnum):
    NEW = "new"
    TESTED = "tested"
    REVIEWED = "reviewed"
    SELECTED = "selected"


class SelectionIntent(StrEnum):
    KEEP = "keep"
    SELECT = "select"


def validate_name(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
        raise ValidationError("Name must contain 1–80 characters after trimming")
    return value.strip()


def validate_rating(value: int | None) -> int | None:
    if value is not None and (type(value) is not int or not 0 <= value <= 100):
        raise ValidationError("Rating must be an integer from 0 to 100, or unrated")
    return value


@dataclass(frozen=True)
class ReviewDraft:
    name: str
    rating: int | None = None
    selection: SelectionIntent = SelectionIntent.KEEP

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_name(self.name))
        validate_rating(self.rating)
        if not isinstance(self.selection, SelectionIntent):
            raise ValidationError("Selection must be Keep or Select")


@dataclass(frozen=True)
class HomeSlot:
    position: int
    game_id: UUID | None = None
    legacy_tile_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.position) is not int or not 1 <= self.position <= 9:
            raise ValidationError("Home position must be an integer from 1 to 9")
        if self.game_id is not None and not isinstance(self.game_id, UUID):
            raise ValidationError("Game identity must be a UUID")
        if self.legacy_tile_id is not None and (
            not isinstance(self.legacy_tile_id, str) or not self.legacy_tile_id.strip()
        ):
            raise ValidationError("Legacy tile identity cannot be empty")
        if self.game_id is not None and self.legacy_tile_id is not None:
            raise ValidationError("A position cannot contain both a game and a legacy activity")


@dataclass(frozen=True)
class ReviewSummary:
    game_id: UUID
    display_name: str
    status: ReviewStatus
    rating: int | None
    revision: int


class CatalogReader(Protocol):
    def get_item(self, game_id: UUID) -> CatalogItem: ...

    def list_games(self) -> tuple[CatalogItem, ...]: ...


class HomeReader(Protocol):
    def list_slots(self) -> tuple[HomeSlot, ...]: ...


class ReviewService(Protocol):
    def save_review(
        self,
        game_id: UUID,
        expected_revision: int,
        draft: ReviewDraft,
        target_slot: int | None = None,
        replacement_confirmation: HomeSlot | None = None,
    ) -> ReviewSummary: ...

    def delete_game(self, game_id: UUID, expected_revision: int) -> None: ...
