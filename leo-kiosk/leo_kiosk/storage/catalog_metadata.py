"""Provider/source-history persistence, independent from parent review updates."""

import sqlite3
from datetime import datetime
from typing import Any
from uuid import UUID

from leo_kiosk.domain.catalog import (
    CatalogItem,
    DimensionEvidence,
    Dimensions,
    MediaType,
    Orientation,
    validate_provider_id,
)
from leo_kiosk.domain.catalog_metadata import ImportRecord, Provider
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import NotFoundError

from ._repository import Repository, decode_record

_MEDIA_TYPES = {member.value: member for member in MediaType}
_ORIENTATIONS = {member.value: member for member in Orientation}
_EVIDENCE = {member.value: member for member in DimensionEvidence}


def _media_type(value: object) -> MediaType:
    """Accept the domain IntEnum values 0/1/2 as integers or names; never strings like 'game'."""
    if isinstance(value, MediaType):
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Media type must be integer 0, 1 or 2")
    return MediaType(value)


def _orientation(value: Any) -> Orientation:
    if isinstance(value, Orientation):
        return value
    if value is None or isinstance(value, bool):
        # Legacy discovery booleans are orientation-unaware, not measured portrait data.
        return Orientation.UNKNOWN
    if isinstance(value, str) and value in _ORIENTATIONS:
        return Orientation(value)
    raise ValueError("Orientation must be a domain value or a legacy boolean placeholder")


def _dimensions(raw: dict[str, Any]) -> Dimensions:
    width, height = raw.get("width"), raw.get("height")
    evidence = raw.get("dimension_evidence", raw.get("evidence"))
    if width is None and height is None:
        return Dimensions(None, None, DimensionEvidence.UNKNOWN)
    if evidence in (None, False, True, ""):  # Sizes without evidence are not measurements.
        raise ValueError("A provided size requires a dimension evidence category")
    return Dimensions(width, height, DimensionEvidence(evidence))


def _launch(raw: dict[str, Any]) -> str | None:
    value = raw.get("launch_url")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Launch override must be a string URL")
    return value


class CatalogMetadataRepository(Repository):
    def upsert_provider(self, provider: Provider) -> None:
        self._write(
            "INSERT INTO providers (id, name, website_url) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, website_url=excluded.website_url",
            (provider.provider_id, provider.name, provider.website_url),
        )

    def get_provider(self, provider_id: str) -> Provider:
        rows = self._rows(
            "SELECT id, name, website_url FROM providers WHERE id = ?",
            (validate_provider_id(provider_id),),
        )
        if not rows:
            raise NotFoundError("Provider not found")
        return self._provider(rows[0])

    def list_providers(self) -> tuple[Provider, ...]:
        return tuple(
            self._provider(row)
            for row in self._rows("SELECT id, name, website_url FROM providers ORDER BY name, id")
        )

    def record_import(self, record: ImportRecord) -> None:
        self._write(
            "INSERT INTO catalog_imports (id, source_checksum, imported_at, report_json) "
            "VALUES (?, ?, ?, ?)",
            (
                str(record.import_id),
                record.source_checksum,
                record.imported_at.isoformat(),
                record.report_json,
            ),
        )

    def get_import(self, import_id: UUID) -> ImportRecord:
        records = self._rows("SELECT * FROM catalog_imports WHERE id = ?", (str(import_id),))
        if not records:
            raise NotFoundError("Catalog import not found")
        return self._import(records[0])

    def list_imports(self) -> tuple[ImportRecord, ...]:
        return tuple(
            self._import(row)
            for row in self._rows("SELECT * FROM catalog_imports ORDER BY imported_at, id")
        )

    @staticmethod
    def _provider(row: sqlite3.Row) -> Provider:
        return decode_record(lambda: Provider(*row))

    @staticmethod
    def _import(row: sqlite3.Row) -> ImportRecord:
        # Row values are validated by the domain constructor, not returned to widgets.
        return decode_record(
            lambda: ImportRecord(
                row["source_checksum"],
                datetime.fromisoformat(row["imported_at"]),
                row["report_json"],
                UUID(row["id"]),
            )
        )

    # --- source adapters: flexible input shapes -> validated DTOs -------------

    @staticmethod
    def provider_from_source(raw: dict[str, Any]) -> Provider:
        try:
            return Provider(raw["provider_id"], raw["name"], raw["website_url"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Source provider requires id, name and website URL") from exc

    @staticmethod
    def game_from_source(raw: dict[str, Any]) -> StoredGame:
        try:
            item = CatalogItem(
                raw["provider_id"],
                raw["source_url"],
                raw["source_name"],
                _media_type(raw.get("media_type", raw.get("type"))),
                _orientation(raw.get("orientation", raw.get("is_landscape"))),
                _dimensions(raw),
                _launch(raw),
            )
            return StoredGame(item, source_metadata_json=raw.get("source_metadata_json") or "{}")
        except (KeyError, TypeError) as exc:
            raise ValueError("Source game requires provider, source URL and name") from exc
