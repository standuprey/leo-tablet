"""Complete immutable persisted catalog values; selection remains a home-slot concern."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .catalog import CatalogItem
from .catalog_metadata import canonical_json_object, validate_utc
from .errors import ValidationError
from .reviews import AgeRange, validate_name, validate_rating


@dataclass(frozen=True)
class StoredGame:
    item: CatalogItem
    parent_name: str | None = None
    rating: int | None = None
    prod_stars: int | None = None
    edu_stars: int | None = None
    fun_stars: int | None = None
    age_min: int | None = None
    age_max: int | None = None
    tested_at: datetime | None = None
    reviewed_at: datetime | None = None
    deleted_at: datetime | None = None
    revision: int = 0
    source_metadata_json: str = "{}"

    def __post_init__(self) -> None:
        if not isinstance(self.item, CatalogItem):
            raise ValidationError("Stored game requires a validated catalog item")
        if self.parent_name is not None:
            object.__setattr__(self, "parent_name", validate_name(self.parent_name))
        validate_rating(self.rating)
        for value in (self.prod_stars, self.edu_stars, self.fun_stars):
            if value is not None and (type(value) is not int or not 0 <= value <= 5):
                raise ValidationError("Star ratings must be integers from 0 to 5")
        if (self.age_min is None) != (self.age_max is None):
            raise ValidationError("An age range requires both bounds")
        if self.age_min is not None and self.age_max is not None:
            AgeRange(self.age_min, self.age_max)  # bounds + order validation
        for timestamp in (self.tested_at, self.reviewed_at, self.deleted_at):
            if timestamp is not None:
                validate_utc(timestamp)
        if type(self.revision) is not int or self.revision < 0:
            raise ValidationError("Review revision must be a nonnegative integer")
        object.__setattr__(
            self, "source_metadata_json", canonical_json_object(self.source_metadata_json)
        )

    @property
    def game_id(self) -> UUID:
        return self.item.game_id

    @property
    def display_name(self) -> str:
        return self.parent_name if self.parent_name is not None else self.item.source_name
