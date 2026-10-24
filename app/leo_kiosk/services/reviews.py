"""Review transactions: metadata + selection + history in one atomic save."""

import json as _json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import ConflictError, ValidationError
from leo_kiosk.domain.reviews import (
    HomeSlot,
    ReviewDraft,
    ReviewStatus,
    ReviewSummary,
    SelectionIntent,
    validate_rating,
)
from leo_kiosk.services.home import HomeService
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.database import transaction

_EVENT_FOR_INTENT = {
    SelectionIntent.KEEP: "reviewed",
    SelectionIntent.SELECT: "selected",
}


class ReviewService:
    def __init__(self, catalog: CatalogRepository, home: HomeService) -> None:
        self._catalog = catalog
        self._home = home

    def save_review(
        self,
        game_id: UUID,
        expected_revision: int,
        draft: ReviewDraft,
        target_slot: int | None = None,
        replacement_confirmation: HomeSlot | None = None,
    ) -> "ReviewSummary":
        record = self._catalog.get_record(game_id)
        if record.deleted_at is not None:
            raise ValidationError("A deleted game cannot be reviewed")
        if expected_revision != record.revision:
            raise ConflictError(
                f"Review changed under you (revision {record.revision} != {expected_revision})"
            )
        validate_rating(draft.rating)
        now = datetime.now(UTC).isoformat()
        with transaction(self._catalog.connection):
            self._catalog.connection.execute(
                "UPDATE games SET parent_name = ?, rating = ?, reviewed_at = ?, "
                "revision = revision + 1 WHERE id = ? AND revision = ?",
                (draft.name, draft.rating, now, str(game_id), expected_revision),
            )
            current_slot = self._home.slot_for_game(game_id)
            if draft.selection is SelectionIntent.KEEP:
                self._home.unselect(game_id)
            elif target_slot is None:
                if current_slot is None:
                    raise ValidationError(
                        "Selecting for the home screen requires choosing one of the 9 positions"
                    )
            else:
                self._home.place(game_id, target_slot, replacement_confirmation)
            self._catalog.connection.execute(
                "INSERT INTO review_events (id, game_id, event_kind, timestamp, change_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    str(game_id),
                    _EVENT_FOR_INTENT[draft.selection],
                    now,
                    _json.dumps({"name": draft.name, "rating": draft.rating}, ensure_ascii=False),
                ),
            )
        record = self._catalog.get_record(game_id)
        return ReviewSummary(
            game_id=game_id,
            display_name=record.display_name,
            status=self._status(record),
            rating=record.rating,
            revision=record.revision,
        )

    def delete_game(self, game_id: UUID, expected_revision: int) -> None:
        record = self._catalog.get_record(game_id)
        if record.deleted_at is not None:
            return  # already tombstoned; idempotent
        if expected_revision != record.revision:
            raise ConflictError(
                f"Review changed under you (revision {record.revision} != {expected_revision})"
            )
        now = datetime.now(UTC).isoformat()
        with transaction(self._catalog.connection):
            # Draft name/rating are NOT saved by the destructive action.
            self._catalog.connection.execute(
                "UPDATE games SET deleted_at = ?, revision = revision + 1 "
                "WHERE id = ? AND revision = ?",
                (now, str(game_id), expected_revision),
            )
            self._home.unselect(game_id)
            self._catalog.connection.execute(
                "INSERT INTO review_events (id, game_id, event_kind, timestamp, change_json) "
                "VALUES (?, ?, 'deleted', ?, ?)",
                (str(uuid4()), str(game_id), now, '{"deleted_by": "parent"}'),
            )

    def restore(self, game_id: UUID) -> None:
        """Clear a tombstone; the game returns as reviewed, never auto-selected."""
        record = self._catalog.get_record(game_id)
        if record.deleted_at is None:
            return
        with transaction(self._catalog.connection):
            self._catalog.connection.execute(
                "UPDATE games SET deleted_at = NULL WHERE id = ?", (str(game_id),)
            )
            self._catalog.connection.execute(
                "INSERT INTO review_events (id, game_id, event_kind, timestamp, change_json) "
                "VALUES (?, ?, 'restored', ?, '{}')",
                (str(uuid4()), str(game_id), datetime.now(UTC).isoformat()),
            )

    def _status(self, record: StoredGame) -> ReviewStatus:
        if self._home.slot_for_game(record.game_id) is not None:
            return ReviewStatus.SELECTED
        return ReviewStatus.REVIEWED
