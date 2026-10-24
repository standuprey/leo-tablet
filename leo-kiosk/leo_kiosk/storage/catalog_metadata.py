"""Provider/source-history persistence, independent from parent review updates."""

import sqlite3
from datetime import datetime
from uuid import UUID

from leo_kiosk.domain.catalog import validate_provider_id
from leo_kiosk.domain.catalog_metadata import ImportRecord, Provider
from leo_kiosk.domain.errors import NotFoundError

from ._repository import Repository, decode_record


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

    @staticmethod
    def _provider(row: sqlite3.Row) -> Provider:
        return decode_record(lambda: Provider(*row))

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
