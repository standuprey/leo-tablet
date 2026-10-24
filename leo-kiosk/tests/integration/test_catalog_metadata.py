from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from leo_kiosk.domain.catalog_metadata import ImportRecord, Provider
from leo_kiosk.domain.errors import NotFoundError, StorageError, ValidationError
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def metadata(tmp_path):
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        yield CatalogMetadataRepository(connection)


def test_provider_upsert_is_parameterized_and_returns_immutable_dtos(metadata):
    provider = Provider("pbs", "  '; DROP TABLE games; --  ", "HTTPS://PBSKIDS.ORG:443")
    with transaction(metadata.connection):
        metadata.upsert_provider(provider)
    assert metadata.get_provider("pbs") == provider
    with pytest.raises(FrozenInstanceError):
        provider.name = "changed"
    updated = Provider("pbs", "PBS Kids", "https://pbskids.org")
    with transaction(metadata.connection):
        metadata.upsert_provider(updated)
    assert metadata.list_providers() == (updated,)
    assert metadata.connection.execute("SELECT count(*) FROM games").fetchone()[0] == 0


def test_import_history_keeps_distinct_events_with_same_source_checksum(metadata):
    first = ImportRecord("a" * 64, datetime(2026, 1, 1, tzinfo=UTC), '{"added": 2}')
    second = ImportRecord(first.source_checksum, datetime(2026, 1, 2, tzinfo=UTC))
    with transaction(metadata.connection):
        metadata.record_import(first)
        metadata.record_import(second)
    assert metadata.get_import(first.import_id) == first
    assert metadata.list_imports() == (first, second)
    with pytest.raises(StorageError):
        with transaction(metadata.connection):
            metadata.record_import(first)
    assert len(metadata.list_imports()) == 2


def test_writes_require_caller_transaction_and_rollback_together(metadata):
    provider = Provider("pbs", "PBS", "https://pbskids.org")
    with pytest.raises(StorageError, match="caller-owned"):
        metadata.upsert_provider(provider)
    with pytest.raises(ValidationError):
        with transaction(metadata.connection):
            metadata.upsert_provider(provider)
            metadata.record_import(ImportRecord("b" * 64, datetime.now(UTC)))
            raise ValidationError("abort source import")
    assert metadata.list_providers() == () and metadata.list_imports() == ()
    with pytest.raises(NotFoundError):
        metadata.get_provider("pbs")
    with pytest.raises(NotFoundError):
        metadata.get_import(uuid4())


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(source_checksum="bad"),
        dict(imported_at=None),
        dict(imported_at=datetime(2026, 1, 1)),
        dict(report_json="[]"),
        dict(report_json="bad"),
        dict(report_json='{"count": NaN}'),
        dict(import_id="not-a-uuid"),
    ],
)
def test_invalid_import_dto(kwargs):
    fields = dict(source_checksum="c" * 64, imported_at=datetime.now(UTC))
    fields.update(kwargs)
    with pytest.raises(ValidationError):
        ImportRecord(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        ("PBS Kids", "PBS", "https://pbskids.org"),
        ("pbs", " ", "https://pbskids.org"),
        ("pbs", "PBS", "javascript:alert(1)"),
    ],
)
def test_invalid_provider_dto(fields):
    with pytest.raises(ValidationError):
        Provider(*fields)
