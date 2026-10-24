"""Typed service errors safe for UI handling (not raw tracebacks)."""


class ValidationError(ValueError):
    """Input violates a domain contract."""


class ConflictError(Exception):
    """The persisted record or occupant changed since it was read."""


class StorageError(Exception):
    """Persistence failed; callers must retain unsaved drafts."""


class NotFoundError(LookupError):
    """A requested catalog record is absent; not an empty or successful result."""
