"""Transactional slot placement: explicit moves, confirmed replacements.

Eligibility (tested-or-reviewed, nondeleted, game media type) is enforced
here so every caller — the review save transaction included — inherits the
same invariants.
"""

from uuid import UUID

from leo_kiosk.domain.errors import ConflictError, ValidationError
from leo_kiosk.domain.reviews import HomeSlot
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.database import transaction
from leo_kiosk.storage.home import HomeRepository


class HomeService:
    def __init__(self, repository: HomeRepository, catalog: CatalogRepository) -> None:
        self._repository = repository
        self._catalog = catalog

    def slots(self) -> tuple[HomeSlot, ...]:
        return self._repository.slots()

    def slot(self, position: int) -> HomeSlot:
        return self._repository.slot(position)

    def slot_for_game(self, game_id: UUID) -> HomeSlot | None:
        return self._repository.slot_for_game(game_id)

    def selected_game_ids(self) -> set[UUID]:
        return self._repository.selected_game_ids()

    def _require_placeable(self, game_id: UUID) -> None:
        record = self._catalog.get_record(game_id)
        if record.deleted_at is not None:
            raise ValidationError("A deleted game cannot occupy a home position")
        if record.tested_at is None and record.reviewed_at is None:
            # A game the parent has at least tried may occupy a slot; fully
            # untested (never launched) games cannot. Owner decision 2026-10-26.
            raise ValidationError("Only a tested game can be selected")
        if record.item.media_type.value != 2:
            raise ValidationError("Only game records can occupy a game position")

    def place(
        self,
        game_id: UUID,
        position: int,
        replacement_confirmation: HomeSlot | None = None,
    ) -> None:
        """Assign game_id to position; a move clears its previous slot.

        Replacing occupied content requires the occupant the caller saw, so a
        concurrent change conflicts instead of silently overwriting.
        """
        self._require_placeable(game_id)
        target = self._repository.slot(position)
        occupant = target.game_id or target.legacy_tile_id
        if occupant is not None and replacement_confirmation != target:
            raise ConflictError(
                f"Replacing position {position} ({occupant!r}) requires explicit confirmation"
            )
        previous = self._repository.slot_for_game(game_id)
        if previous is not None and previous.position == position:
            return  # already there
        with transaction(self._repository.connection, join=True):
            # Clear first: game_id is UNIQUE across slots, so a move must
            # release the old position before claiming the new one.
            if previous is not None:
                self._repository.clear(previous.position)
            self._repository.set_game(position, game_id)

    def unselect(self, game_id: UUID) -> bool:
        """Remove the game from its slot, leaving the position empty."""
        previous = self._repository.slot_for_game(game_id)
        if previous is None:
            return False
        with transaction(self._repository.connection, join=True):
            self._repository.clear(previous.position)
        return True
