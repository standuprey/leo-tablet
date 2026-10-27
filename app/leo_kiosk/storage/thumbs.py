"""Thumbnail-file persistence: which game has art and when it was taken.

The PNG bytes live in a filesystem directory (thumbs/ next to the catalog
database, XDG-convention path); the row is the authority that art exists.
Writes happen in caller-owned transactions; the file write is deliberately
NOT transactional against the row — an orphaned PNG without a row is
harmless, a row without a readable PNG must be tolerated by readers.
"""

import sqlite3
from datetime import datetime
from uuid import UUID

from leo_kiosk.domain.errors import NotFoundError

from ._repository import Repository


class ThumbnailRepository(Repository):
    def record(self, game_id: UUID, taken_at: datetime) -> None:
        """Latest-wins upsert; a re-shoot overwrites the row and the file."""
        self._write(
            "INSERT INTO game_thumbnails (game_id, taken_at) VALUES (?, ?) "
            "ON CONFLICT (game_id) DO UPDATE SET taken_at = excluded.taken_at",
            (str(game_id), taken_at.isoformat()),
        )

    def has_thumbnail(self, game_id: UUID) -> bool:
        rows = self._rows(
            "SELECT 1 FROM game_thumbnails WHERE game_id = ?", (str(game_id),)
        )
        return bool(rows)

    def taken_at(self, game_id: UUID) -> datetime:
        rows = self._rows(
            "SELECT taken_at FROM game_thumbnails WHERE game_id = ?", (str(game_id),)
        )
        if not rows:
            raise NotFoundError("No thumbnail for game")
        return datetime.fromisoformat(rows[0]["taken_at"])

    def forget(self, connection: sqlite3.Connection, game_id: UUID) -> bool:
        """Direct delete for recovery/testing; production deletes cascade."""
        cursor = connection.execute(
            "DELETE FROM game_thumbnails WHERE game_id = ?", (str(game_id),)
        )
        return cursor.rowcount > 0
