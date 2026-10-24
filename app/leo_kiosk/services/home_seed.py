"""Seed the nine legacy home activities exactly once, from trusted config.

tiles.json is administrator-owned: only it can define executable commands.
The catalog can never inject one. Seeding runs once on an empty table and
never overwrites a parent replacement.
"""

import json
import sqlite3
from pathlib import Path

from leo_kiosk.domain.errors import StorageError, ValidationError
from leo_kiosk.storage.database import transaction

_REQUIRED = ("id", "label", "color", "cmd", "minutes")


def load_legacy_tiles(path: Path) -> list[dict[str, object]]:
    """Validate the trusted config; reject partial/malformed without seeding."""
    try:
        cfg = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Cannot read trusted tile config {path}: {exc}") from exc
    tiles = cfg.get("tiles")
    if not isinstance(tiles, list) or not 1 <= len(tiles) <= 9:
        raise ValidationError("Trusted tiles must contain 1-9 entries")
    seen: set[str] = set()
    for tile in tiles:
        if not isinstance(tile, dict) or any(key not in tile for key in _REQUIRED):
            raise ValidationError(f"Legacy tile missing required keys: {tile!r}")
        tile_id = tile["id"]
        if not isinstance(tile_id, str) or not tile_id.strip() or tile_id in seen:
            raise ValidationError(f"Legacy tile id must be a unique nonempty slug: {tile_id!r}")
        seen.add(tile_id)
        if not isinstance(tile["label"], str) or not tile["label"].strip():
            raise ValidationError("Legacy tile label cannot be empty")
        if not isinstance(tile["color"], str) or not tile["color"].startswith("#"):
            raise ValidationError("Legacy tile color must be a hex string")
        cmd = tile["cmd"]
        if (
            not isinstance(cmd, list)
            or not cmd
            or not all(isinstance(arg, str) and arg for arg in cmd)
        ):
            raise ValidationError("Legacy tile cmd must be a nonempty argv list")
        alt = tile.get("alt")
        if alt is not None and (
            not isinstance(alt, list) or not all(isinstance(arg, str) for arg in alt)
        ):
            raise ValidationError("Legacy tile alt must be an argv list")
        minutes = tile["minutes"]
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 < minutes <= 120:
            raise ValidationError("Legacy tile minutes must be an integer from 1 to 120")
    return tiles


def seed_home(connection: sqlite3.Connection, tiles_path: Path) -> bool:
    """Insert the nine legacy positions exactly once.

    Returns True when seeding happened. Any pre-existing occupied row (already
    seeded, or a parent replacement) is never touched.
    """
    occupied = connection.execute(
        "SELECT count(*) FROM home_slots WHERE legacy_tile_id IS NOT NULL"
    ).fetchone()[0]
    if occupied:
        return False
    tiles = load_legacy_tiles(tiles_path)
    with transaction(connection):
        # Re-check inside the transaction: something may have been placed
        # between the outside check and the write lock.
        placed = connection.execute(
            "SELECT count(*) FROM home_slots WHERE legacy_tile_id IS NOT NULL"
        ).fetchone()[0]
        if placed:
            return False
        for position, tile in enumerate(tiles, 1):
            connection.execute(
                "INSERT INTO home_slots (position, legacy_tile_id, legacy_tile_json) "
                "VALUES (?, ?, ?)",
                (position, tile["id"], json.dumps(tile, ensure_ascii=False)),
            )
    return True
