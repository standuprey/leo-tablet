"""Bootstrap/source catalog import: one transaction, source fields only."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from leo_kiosk.domain.catalog_metadata import ImportRecord
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import transaction


class BootstrapSource(Protocol):
    """A validated catalog snapshot; the old JSON shape is not a contract."""

    @property
    def checksum(self) -> str: ...

    @property
    def providers(self) -> tuple[dict[str, Any], ...]: ...

    @property
    def games(self) -> tuple[dict[str, Any], ...]: ...


@dataclass(frozen=True)
class ImportReport:
    source_checksum: str
    imported_at: str
    added: int
    updated: int
    unchanged: int
    preserved_local: int
    purged: int = 0

    def as_json(self) -> str:
        return json.dumps(
            {
                "added": self.added,
                "updated": self.updated,
                "unchanged": self.unchanged,
                "preserved_local": self.preserved_local,
                "purged": self.purged,
            },
            sort_keys=True,
        )


def _validate_source_records(
    source: BootstrapSource,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Structural validation only; domain constructors revalidate inside the transaction."""
    checksum = source.checksum
    if not isinstance(checksum, str) or not checksum:
        raise ValidationError("Source checksum is required")
    providers = source.providers
    games = source.games
    if not isinstance(providers, tuple) or not isinstance(games, tuple):
        raise ValidationError("Bootstrap source must expose provider and game tuples")
    return list(providers), list(games)


def import_catalog(connection: sqlite3.Connection, source: BootstrapSource) -> ImportReport:
    """Populate the authoritative store; parent decisions, slots and history stay untouched."""
    provider_rows, game_rows = _validate_source_records(source)
    metadata = CatalogMetadataRepository(connection)
    catalog = CatalogRepository(connection)
    if not provider_rows:
        raise ValidationError("A source snapshot without providers is incomplete")
    existing = {
        UUID(row["id"]): row
        for row in connection.execute(
            "SELECT id, source_name, launch_url, media_type, orientation, width, height, "
            "dimension_evidence, source_metadata_json, parent_name, rating, tested_at, "
            "reviewed_at, deleted_at, revision FROM games"
        )
    }
    known_providers = {row[0] for row in connection.execute("SELECT id FROM providers")}
    added = updated = unchanged = preserved_local = purged = 0
    with transaction(connection):
        for raw in provider_rows:
            metadata.upsert_provider(CatalogMetadataRepository.provider_from_source(raw))
            known_providers.add(raw["provider_id"])
        for raw in game_rows:
            if raw.get("provider_id") not in known_providers:
                raise ValidationError(
                    f"Source game references an unlisted provider: {raw.get('provider_id')!r}"
                )
            record = CatalogMetadataRepository.game_from_source(raw)
            current = existing.pop(record.game_id, None)
            if current is None:
                catalog.insert_record(record)
                added += 1
            else:
                changes = _source_changes(record, current)
                if changes:
                    catalog.refresh_source_fields(record.game_id, changes)
                    updated += 1
                else:
                    unchanged += 1
        # Records removed from the source stay until the parent decides:
        # trialed/reviewed games are always preserved; never-touched games are
        # soft-deleted (tombstoned) so they leave the review queue, and
        # reimports cannot resurrect them. Games occupying a home slot are
        # left visible; unselecting them is the parent's call.
        for game_id, row in existing.items():
            if row["tested_at"] is not None or row["reviewed_at"] is not None:
                preserved_local += 1
                continue
            assigned = connection.execute(
                "SELECT 1 FROM home_slots WHERE game_id = ?", (str(game_id),)
            ).fetchone()
            if assigned:
                preserved_local += 1
                continue
            connection.execute(
                "UPDATE games SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (datetime.now(UTC).isoformat(), str(game_id)),
            )
            connection.execute(
                "INSERT INTO review_events (id, game_id, event_kind, timestamp, change_json) "
                "VALUES (?, ?, 'deleted', ?, ?)",
                (
                    str(uuid4()),
                    str(game_id),
                    datetime.now(UTC).isoformat(),
                    '{"auto": "removed-from-source"}',
                ),
            )
            purged += 1
        report = ImportReport(
            source.checksum,
            datetime.now(UTC).isoformat(),
            added,
            updated,
            unchanged,
            preserved_local,
            purged,
        )
        metadata.record_import(
            ImportRecord(
                report.source_checksum,
                datetime.now(UTC),
                report.as_json(),
            )
        )
    return report


def _source_changes(record: StoredGame, current: sqlite3.Row) -> dict[str, object]:
    """Source-owned columns only; parent_name/rating/history/revision never change."""
    item = record.item
    changes: dict[str, object] = {}
    for column, value in [
        ("source_name", item.source_name),
        ("launch_url", item.launch_url),
        ("media_type", int(item.media_type)),
        ("orientation", item.orientation.value),
        ("width", item.dimensions.width),
        ("height", item.dimensions.height),
        ("dimension_evidence", item.dimensions.evidence.value),
        ("source_metadata_json", record.source_metadata_json),
    ]:
        if current[column] != value:
            changes[column] = value
    return changes
