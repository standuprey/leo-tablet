"""Launch-session persistence: history only, never an actionable PID store."""

import sqlite3
from datetime import datetime
from uuid import UUID

from leo_kiosk.domain.errors import NotFoundError

from ._repository import Repository


class SessionRepository(Repository):
    def start_session(
        self, token: UUID, game_id: UUID | None, slot: int | None, role: str, started_at: datetime
    ) -> None:
        self._write(
            "INSERT INTO launch_sessions (id, game_id, slot, role, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(token), str(game_id) if game_id else None, slot, role, started_at.isoformat()),
        )

    def finish_session(
        self, token: UUID, ended_at: datetime, outcome: str, failure_reason: str | None = None
    ) -> None:
        self._write(
            "UPDATE launch_sessions SET ended_at = ?, outcome = ?, failure_reason = ? WHERE id = ?",
            (ended_at.isoformat(), outcome, failure_reason, str(token)),
        )

    def mark_abandoned(self, ended_at: datetime) -> int:
        """Recovery: finish sessions left open by a previous process."""
        cursor = self._rows("SELECT id FROM launch_sessions WHERE ended_at IS NULL")
        for row in cursor:
            self._write(
                "UPDATE launch_sessions SET ended_at = ?, outcome = ? WHERE id = ?",
                (ended_at.isoformat(), "abandoned", row["id"]),
            )
        return len(cursor)

    def get_session(self, token: UUID) -> sqlite3.Row:
        rows = self._rows("SELECT * FROM launch_sessions WHERE id = ?", (str(token),))
        if not rows:
            raise NotFoundError("Launch session not found")
        return rows[0]
