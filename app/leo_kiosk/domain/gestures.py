"""Pure volume-tap recognizer. No device access, signals or UI side effects.

Enabled patterns are context-owned: a Down/Up return exists for review trials
and must never be enabled alongside Down/Down/Up, which it would match first.
"""

import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class VolumeKey(IntEnum):
    DOWN = 114
    UP = 115


class GestureAction(StrEnum):
    ENTER_PARENT = "enter_parent"
    RETURN = "return"
    SCREENSHOT = "screenshot"


@dataclass(frozen=True)
class GestureConfig:
    max_gap: float = 1.0
    max_duration: float = 2.0
    cooldown: float = 0.5

    def __post_init__(self) -> None:
        for name in ("max_gap", "max_duration", "cooldown"):
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value < 0
                or (name != "cooldown" and value == 0)
            ):
                raise ValueError(f"Invalid gesture timing: {name}")


# Default set: parent entry from the child surface and return from parent surfaces.
UDD = (VolumeKey.UP, VolumeKey.DOWN, VolumeKey.DOWN)
DDU = (VolumeKey.DOWN, VolumeKey.DOWN, VolumeKey.UP)
DU = (VolumeKey.DOWN, VolumeKey.UP)
DD = (VolumeKey.DOWN, VolumeKey.DOWN)

DEFAULT_PATTERNS: tuple[tuple[tuple[VolumeKey, ...], GestureAction], ...] = (
    (UDD, GestureAction.ENTER_PARENT),
    (DDU, GestureAction.RETURN),
)
# Parent/video surfaces: the short Down/Up return replaces DDU there (the
# web port made these launcher-owned pages; backwatch no longer exits them).
# DU must not be enabled alongside DDU, which it would match first.
PARENT_SURFACE_PATTERNS: tuple[tuple[tuple[VolumeKey, ...], GestureAction], ...] = (
    (DU, GestureAction.RETURN),
    (UDD, GestureAction.ENTER_PARENT),
)
REVIEW_TRIAL_PATTERNS: tuple[tuple[tuple[VolumeKey, ...], GestureAction], ...] = (
    # Exiting a game under review uses the short Down/Up return.
    (DU, GestureAction.RETURN),
    # Down/Down captures a thumbnail; it diverges from DU at the second key,
    # so both coexist here (the ambiguity gate only rejects prefixes).
    (DD, GestureAction.SCREENSHOT),
)


class GestureRecognizer:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        config: GestureConfig | None = None,
        patterns: Iterable[tuple[tuple[VolumeKey, ...], GestureAction]] = DEFAULT_PATTERNS,
    ) -> None:
        self.clock = clock
        self.config = config or GestureConfig()
        self._patterns = self._validate(patterns)
        self._buffer: list[tuple[VolumeKey, float]] = []
        self._cooldown_until = -math.inf
        self._last_time: float | None = None
        self.last_reset_reason: str | None = None

    @staticmethod
    def _validate(
        patterns: Iterable[tuple[tuple[VolumeKey, ...], GestureAction]],
    ) -> tuple[tuple[tuple[VolumeKey, ...], GestureAction], ...]:
        ordered = tuple(patterns)
        if not ordered:
            raise ValueError("At least one gesture pattern is required")
        seen: set[tuple[VolumeKey, ...]] = set()
        for sequence, action in ordered:
            if (
                not isinstance(sequence, tuple)
                or len(sequence) < 2  # A one-key pattern would swallow every volume tap.
                or not all(type(key) is VolumeKey for key in sequence)
                or not isinstance(action, GestureAction)
            ):
                raise ValueError("Patterns require VolumeKey sequences and GestureActions")
            if sequence in seen:
                raise ValueError("Duplicate gesture pattern")
            seen.add(sequence)
        # Ambiguity gate: no enabled pattern may be a prefix of another enabled
        # pattern; the shorter would always win and shadow the longer. Note that
        # DU and DDU are NOT ambiguous (they diverge at the second key), so both
        # may coexist geometrically. Product-level separation — never enabling
        # the short return outside review trials — is the adapter's contract.
        for left in seen:
            for right in seen:
                if left != right and right[: len(left)] == left:
                    raise ValueError(f"Ambiguous pattern set: {left} prefixes {right}")
        return ordered

    def use_patterns(self, patterns: Iterable[tuple[tuple[VolumeKey, ...], GestureAction]]) -> None:
        """Swap context-owned pattern sets (callers reset explicitly if wanted)."""
        self._patterns = self._validate(patterns)

    @property
    def patterns(self) -> tuple[tuple[tuple[VolumeKey, ...], GestureAction], ...]:
        return self._patterns

    def reset(self, reason: str) -> None:
        """Discard partial taps, but preserve cooldown across a route change."""
        self._buffer.clear()
        self.last_reset_reason = reason

    def feed(self, code: int, value: int = 1) -> GestureAction | None:
        if type(value) is not int or value != 1 or code not in (VolumeKey.UP, VolumeKey.DOWN):
            return None
        key = VolumeKey(code)
        now = self.clock()
        if not math.isfinite(now):
            raise ValueError("Gesture clock must return finite time")
        if self._last_time is not None and now < self._last_time:
            self.reset("clock_moved_backwards")
            self._cooldown_until = -math.inf
        self._last_time = now
        if now < self._cooldown_until:
            return None
        if self._buffer and now - self._buffer[-1][1] > self.config.max_gap:
            self.reset("gap_timeout")
        self._buffer = [(k, t) for k, t in self._buffer if now - t <= self.config.max_duration]
        self._buffer.append((key, now))
        keys = tuple(k for k, _ in self._buffer)
        actions = dict(self._patterns)
        if keys in actions:
            action = actions[keys]
            self.reset("matched")
            self._cooldown_until = now + self.config.cooldown
            return action
        enabled_prefixes = {
            pattern[:length] for pattern, _ in self._patterns for length in range(1, len(pattern))
        }
        for index in range(len(keys)):
            if keys[index:] in enabled_prefixes:
                self._buffer = self._buffer[index:]
                break
        else:
            self._buffer.clear()
        return None
