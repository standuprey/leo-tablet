"""Catalog persistence only: no import upserts, selection policy or hidden commits."""

import sqlite3
from datetime import datetime
from uuid import UUID

from leo_kiosk.domain.catalog import (
    CatalogItem,
    DimensionEvidence,
    Dimensions,
    MediaType,
    Orientation,
)
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import NotFoundError, ValidationError

from ._repository import Repository, decode_record


def _record(row: sqlite3.Row) -> StoredGame:
    item = CatalogItem(
        row["provider_id"],
        row["canonical_source_url"],
        row["source_name"],
        MediaType(row["media_type"]),
        Orientation(row["orientation"]),
        Dimensions(row["width"], row["height"], DimensionEvidence(row["dimension_evidence"])),
        row["launch_url"],
    )
    if UUID(row["id"]) != item.game_id:
        raise ValidationError("Stored game identity does not match its source")
    timestamps = tuple(
        datetime.fromisoformat(row[key]) if row[key] is not None else None
        for key in ("tested_at", "reviewed_at", "deleted_at")
    )
    return StoredGame(
        item,
        parent_name=row["parent_name"],
        rating=row["rating"],
        tested_at=timestamps[0],
        reviewed_at=timestamps[1],
        deleted_at=timestamps[2],
        revision=row["revision"],
        source_metadata_json=row["source_metadata_json"],
    )


class CatalogRepository(Repository):
    def insert_record(self, record: StoredGame) -> None:
        """Insert only; refreshing source fields must never replace parent decisions."""
        item = record.item
        times = tuple(
            value.isoformat() if value is not None else None
            for value in (record.tested_at, record.reviewed_at, record.deleted_at)
        )
        self._write(
            "INSERT INTO games (id, provider_id, canonical_source_url, launch_url, source_name, "
            "media_type, orientation, width, height, dimension_evidence, source_metadata_json, "
            "parent_name, rating, tested_at, reviewed_at, deleted_at, revision) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(item.game_id),
                item.provider_id,
                item.source_url,
                item.launch_url,
                item.source_name,
                int(item.media_type),
                item.orientation.value,
                item.dimensions.width,
                item.dimensions.height,
                item.dimensions.evidence.value,
                record.source_metadata_json,
                record.parent_name,
                record.rating,
                *times,
                record.revision,
            ),
        )

    def get_record(self, game_id: UUID) -> StoredGame:
        rows = self._rows("SELECT * FROM games WHERE id = ?", (str(game_id),))
        if not rows:
            raise NotFoundError("Game not found")
        return decode_record(lambda: _record(rows[0]))

    def get_item(self, game_id: UUID) -> CatalogItem:
        return self.get_record(game_id).item

    def list_records(self, *, include_deleted: bool = False) -> tuple[StoredGame, ...]:
        """List source records of all media types, not an approved/playable queue."""
        condition = "" if include_deleted else "WHERE games.deleted_at IS NULL "
        rows = self._rows(
            "SELECT games.* FROM games JOIN providers ON providers.id = games.provider_id "
            + condition
            + "ORDER BY providers.name, games.source_name, games.id"
        )
        return tuple(self._decode(row) for row in rows)

    def refresh_source_fields(self, game_id: UUID, changes: dict[str, object]) -> None:
        """Update source-owned columns only; caller owns the transaction and rollback."""
        if not changes or set(changes) - {
            "source_name",
            "launch_url",
            "media_type",
            "orientation",
            "width",
            "height",
            "dimension_evidence",
            "source_metadata_json",
        }:
            raise ValidationError("Only source-owned columns may be refreshed")
        assignments = ", ".join(f"{column} = ?" for column in changes)
        self._write(
            f"UPDATE games SET {assignments} WHERE id = ?",
            (*changes.values(), str(game_id)),
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> StoredGame:
        return decode_record(lambda: _record(row))
