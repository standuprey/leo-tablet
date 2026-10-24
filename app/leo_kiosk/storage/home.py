"""Home-slot persistence: constrained updates, DTO reads; no eligibility policy."""

import json
import sqlite3
from uuid import UUID

from leo_kiosk.domain.errors import NotFoundError
from leo_kiosk.domain.reviews import HomeSlot

from ._repository import Repository, decode_record


def _slot(row: sqlite3.Row) -> HomeSlot:
    game_id = row["game_id"]
    legacy_json = row["legacy_tile_json"]

    def build() -> HomeSlot:
        return HomeSlot(
            row["position"],
            game_id=UUID(game_id) if game_id else None,
            legacy_tile_id=row["legacy_tile_id"],
        )

    slot = decode_record(build)
    if legacy_json is not None:
        json.loads(legacy_json)  # stored trusted config must remain valid JSON
    return slot


class HomeRepository(Repository):
    def slots(self) -> tuple[HomeSlot, ...]:
        return tuple(_slot(row) for row in self._rows("SELECT * FROM home_slots ORDER BY position"))

    def slot(self, position: int) -> HomeSlot:
        rows = self._rows("SELECT * FROM home_slots WHERE position = ?", (position,))
        if not rows:
            raise NotFoundError("Home position not found")
        return _slot(rows[0])

    def slot_for_game(self, game_id: UUID) -> HomeSlot | None:
        rows = self._rows("SELECT * FROM home_slots WHERE game_id = ?", (str(game_id),))
        return _slot(rows[0]) if rows else None

    def selected_game_ids(self) -> set[UUID]:
        return {slot.game_id for slot in self.slots() if slot.game_id is not None}

    def set_game(self, position: int, game_id: UUID) -> None:
        self._write(
            "UPDATE home_slots SET game_id = ?, legacy_tile_id = NULL, "
            "legacy_tile_json = NULL WHERE position = ?",
            (str(game_id), position),
        )

    def clear(self, position: int) -> None:
        self._write(
            "UPDATE home_slots SET game_id = NULL, legacy_tile_id = NULL, "
            "legacy_tile_json = NULL WHERE position = ?",
            (position,),
        )

    def count_occupied(self) -> int:
        return int(
            self._rows(
                "SELECT count(*) FROM home_slots WHERE game_id IS NOT NULL "
                "OR legacy_tile_id IS NOT NULL"
            )[0][0]
        )
