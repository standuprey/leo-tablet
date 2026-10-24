"""Immutable provider/import metadata shared by storage and the later importer."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from .catalog import canonicalize_url, validate_provider_id
from .errors import ValidationError


def canonical_json_object(value: str) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError
        result = json.dumps(
            parsed, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        result.encode("utf-8")
        return result
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValidationError("Metadata must be a finite, UTF-8 JSON object") from exc


def validate_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValidationError("Catalog history must use timezone-aware UTC timestamps")
    return value


@dataclass(frozen=True)
class Provider:
    provider_id: str
    name: str
    website_url: str

    def __post_init__(self) -> None:
        validate_provider_id(self.provider_id)
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Provider name cannot be empty")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "website_url", canonicalize_url(self.website_url))


@dataclass(frozen=True)
class ImportRecord:
    source_checksum: str
    imported_at: datetime
    report_json: str = "{}"
    import_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.import_id, UUID):
            raise ValidationError("Import identity must be a UUID")
        if not isinstance(self.source_checksum, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.source_checksum
        ):
            raise ValidationError("Import checksum must be a lowercase SHA-256 digest")
        validate_utc(self.imported_at)
        object.__setattr__(self, "report_json", canonical_json_object(self.report_json))
