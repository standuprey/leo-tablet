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
class AgeRange:
    """Parent-decided recommended age range, in years; both ends required."""

    min_years: int
    max_years: int

    def __post_init__(self) -> None:
        for value in (self.min_years, self.max_years):
            if type(value) is not int or not 1 <= value <= 17:
                raise ValidationError("Age bounds must be integers from 1 to 17")
        if self.min_years > self.max_years:
            raise ValidationError("Age range minimum must not exceed maximum")

    def __str__(self) -> str:
        if self.min_years == self.max_years:
            return f"ages {self.min_years}"
        return f"ages {self.min_years}-{self.max_years}"


@dataclass(frozen=True)
class StarRating:
    """Parent-decided five-star rating on three dimensions (each 0-5)."""

    production: int
    education: int
    fun: int

    def __post_init__(self) -> None:
        for value in (self.production, self.education, self.fun):
            if type(value) is not int or not 0 <= value <= 5:
                raise ValidationError("Star ratings must be integers from 0 to 5")

    def __str__(self) -> str:
        return f"★{self.fun}/{self.education}/{self.production}"


@dataclass(frozen=True)
class ReviewDraft:
    name: str
    rating: int | None = None  # legacy 0-100; superseded by stars
    selection: SelectionIntent = SelectionIntent.KEEP
    age: "AgeRange | None" = None
    stars: "StarRating | None" = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_name(self.name))
        validate_rating(self.rating)
        if self.age is not None and not isinstance(self.age, AgeRange):
            raise ValidationError("Age range must be an AgeRange or unset")
        if self.stars is not None and not isinstance(self.stars, StarRating):
            raise ValidationError("Star rating must be a StarRating or unset")
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
