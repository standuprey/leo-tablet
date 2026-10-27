"""Shared parameter/error boundary; repositories never commit or open transactions."""

import sqlite3
from collections.abc import Callable
from typing import TypeVar

from leo_kiosk.domain.errors import StorageError

T = TypeVar("T")


def decode_record(factory: Callable[[], T]) -> T:
    try:
        return factory()
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise StorageError("Stored catalog metadata is invalid") from exc


class Repository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def _rows(self, sql: str, values: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        try:
            return self.connection.execute(sql, values).fetchall()
        except (sqlite3.Error, UnicodeError, OverflowError) as exc:
            raise StorageError("Cannot read catalog data") from exc

    def _write(self, sql: str, values: tuple[object, ...]) -> sqlite3.Cursor:
        try:
            if not self.connection.in_transaction:
                raise StorageError("Repository writes require a caller-owned transaction")
            return self.connection.execute(sql, values)
        except (sqlite3.Error, UnicodeError, OverflowError) as exc:
            raise StorageError("Cannot write catalog data") from exc
