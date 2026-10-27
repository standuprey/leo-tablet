"""Catalog queries for the review UI: eligibility, status badges, evidence."""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from leo_kiosk.domain.catalog import Dimensions, MediaType
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.reviews import ReviewStatus, StarRating
from leo_kiosk.storage.catalog import CatalogRepository


@dataclass(frozen=True)
class ReviewEntry:
    game_id: UUID
    display_name: str
    status: ReviewStatus
    stars: "StarRating | None"
    age_min: int | None
    age_max: int | None
    provider_id: str
    orientation: str
    dimensions_text: str
    playable_url: str
    dimensions: "Dimensions | None" = None


class CatalogService:
    """Read-side service; no writes, no process control."""

    def __init__(
        self, repository: CatalogRepository, selected_game_ids: Iterable[UUID] = ()
    ) -> None:
        self._repository = repository
        # Selection is derived from home slots; until the home repository lands,
        # callers may inject the selected id set (empty by default).
        self._selected = set(selected_game_ids or ())

    def refresh_selection(self, selected_game_ids: Iterable[UUID]) -> None:
        self._selected = set(selected_game_ids)

    def status(self, record: StoredGame) -> ReviewStatus:
        if record.game_id in self._selected:
            return ReviewStatus.SELECTED
        if record.reviewed_at is not None:
            return ReviewStatus.REVIEWED
        if record.tested_at is not None:
            return ReviewStatus.TESTED
        return ReviewStatus.NEW

    @staticmethod
    def is_playable(record: StoredGame) -> bool:
        return record.item.media_type is MediaType.GAME and record.deleted_at is None

    def list_review_entries(self) -> tuple[ReviewEntry, ...]:
        """Playable games in deterministic provider/name/identity order."""
        entries = []
        for record in self._repository.list_records():
            if not self.is_playable(record):
                continue
            item = record.item
            dimensions = item.dimensions
            if dimensions.width is None:
                dimensions_text = "size unknown"
            else:
                dimensions_text = (
                    f"{dimensions.width}x{dimensions.height} ({dimensions.evidence.value})"
                )
            entries.append(
                ReviewEntry(
                    game_id=item.game_id,
                    display_name=record.display_name,
                    status=self.status(record),
                    stars=(
                        StarRating(record.prod_stars, record.edu_stars, record.fun_stars)
                        if record.prod_stars is not None
                        and record.edu_stars is not None
                        and record.fun_stars is not None
                        else None
                    ),
                    age_min=record.age_min,
                    age_max=record.age_max,
                    provider_id=item.provider_id,
                    orientation=item.orientation.value,
                    dimensions_text=dimensions_text,
                    playable_url=item.playable_url,
                    dimensions=item.dimensions,
                )
            )
        return tuple(entries)

    def get_entry(self, game_id: UUID) -> ReviewEntry:
        record = self._repository.get_record(game_id)
        if not self.is_playable(record):
            raise ValueError("Record is not a playable game")
        return self.list_entry_for(record)

    def list_entry_for(self, record: StoredGame) -> ReviewEntry:
        for entry in self.list_review_entries():
            if entry.game_id == record.game_id:
                return entry
        item = record.item
        return ReviewEntry(
            game_id=item.game_id,
            display_name=record.display_name,
            status=self.status(record),
            stars=None,
            age_min=record.age_min,
            age_max=record.age_max,
            provider_id=item.provider_id,
            orientation=item.orientation.value,
            dimensions_text="size unknown",
            playable_url=item.playable_url,
            dimensions=item.dimensions,
        )
