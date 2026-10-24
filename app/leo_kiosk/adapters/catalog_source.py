"""Adapts catalog/bootstrap.json into the import source protocol."""

import hashlib
import json
from pathlib import Path
from typing import Any

from leo_kiosk.domain.errors import ValidationError

SUPPORTED_BOOTSTRAP_VERSION = 1


class BootstrapCatalogSource:
    """Flexible discovery inputs are gone; this is the versioned deploy asset."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Cannot read bootstrap catalog: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValidationError("Bootstrap root must be an object")
        version = payload.get("bootstrap_version")
        if version != SUPPORTED_BOOTSTRAP_VERSION:
            raise ValidationError(f"Unsupported bootstrap version: {version!r}")
        body = {k: v for k, v in payload.items() if k != "source_sha256"}
        expected = payload.get("source_sha256", "")
        actual = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if expected != actual:
            raise ValidationError("Bootstrap checksum mismatch; asset is corrupted")
        self._payload = payload

    @property
    def checksum(self) -> str:
        return str(self._payload["source_sha256"])

    @property
    def providers(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(p) for p in self._payload.get("providers", []))

    @property
    def games(self) -> tuple[dict[str, Any], ...]:
        flattened = []
        for raw in self._payload.get("games", []):
            game = dict(raw)
            dimensions = game.pop("dimensions", None) or {}
            game["width"] = dimensions.get("width")
            game["height"] = dimensions.get("height")
            game["dimension_evidence"] = dimensions.get("evidence", "unknown")
            flattened.append(game)
        return tuple(flattened)
