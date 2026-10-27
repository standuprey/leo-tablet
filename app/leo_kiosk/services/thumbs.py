"""Thumbnail write service: capture outcome to file + database, latest wins.

Owns nothing visual — the caller produces the PNG bytes (the window's
snapshot callback via the cairo adapter). The service validates, writes
the file into the thumbs directory and records the row in one transaction.
File-then-row order: a crash between them leaves an orphaned PNG, which
readers ignore; a row without a file must never exist.
"""

import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.storage.database import transaction
from leo_kiosk.storage.thumbs import ThumbnailRepository

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def thumbs_directory(database_path: Path) -> Path:
    """Thumbs live next to the catalog database (XDG-convention device path)."""
    return database_path.parent / "thumbs"


class ThumbnailWriter:
    def __init__(
        self,
        repository: ThumbnailRepository,
        directory: Path,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._directory = directory
        self._clock = clock

    def save(self, game_id: UUID, png_bytes: bytes) -> None:
        """Persist one capture; later captures replace earlier ones."""
        if png_bytes[:8] != PNG_MAGIC:
            raise ValidationError("Thumbnail payload must be a PNG image")
        self._directory.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: a partially written file can never be served.
        handle, temp_name = tempfile.mkstemp(
            prefix=f"{game_id.hex}-", suffix=".png", dir=self._directory
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(handle, "wb") as temp_file:
                temp_file.write(png_bytes)
            target = self._directory / f"{game_id}.png"
            os.replace(temp_path, target)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise
        now = self._clock()
        try:
            with transaction(self._repository.connection):
                self._repository.record(game_id, now)
        except Exception:
            # Roll back the orphaned file so state stays rowless-and-clean.
            (self._directory / f"{game_id}.png").unlink(missing_ok=True)
            raise

    def path_for(self, game_id: UUID) -> Path | None:
        """The art path when a thumbnail exists; readers check readability."""
        if not self._repository.has_thumbnail(game_id):
            return None
        return self._directory / f"{game_id}.png"