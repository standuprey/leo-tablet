"""Pure volume-tap recognizer. No device access, signals or UI side effects."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class VolumeKey(IntEnum):
    DOWN = 114
    UP = 115


class GestureAction(StrEnum):
    ENTER_PARENT = "enter_parent"
    RETURN = "return"


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


_PATTERNS = {
    (VolumeKey.UP, VolumeKey.DOWN, VolumeKey.DOWN): GestureAction.ENTER_PARENT,
    (VolumeKey.DOWN, VolumeKey.DOWN, VolumeKey.UP): GestureAction.RETURN,
}
_PREFIXES = {pattern[:length] for pattern in _PATTERNS for length in (1, 2)}


class GestureRecognizer:
    def __init__(
        self, clock: Callable[[], float] = time.monotonic, config: GestureConfig | None = None
    ) -> None:
        self.clock = clock
        self.config = config or GestureConfig()
        self._buffer: list[tuple[VolumeKey, float]] = []
        self._cooldown_until = -math.inf
        self._last_time: float | None = None
        self.last_reset_reason: str | None = None

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
        if keys in _PATTERNS:
            action = _PATTERNS[keys]
            self.reset("matched")
            self._cooldown_until = now + self.config.cooldown
            return action
        for index in range(len(keys)):
            if keys[index:] in _PREFIXES:
                self._buffer = self._buffer[index:]
                break
        else:
            self._buffer.clear()
        return None
