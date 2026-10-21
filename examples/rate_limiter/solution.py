"""Token-bucket rate limiter."""

import time
from collections.abc import Callable


class TokenBucket:
    """Allows bursts of up to `capacity` requests, refilling at a steady rate."""

    def __init__(self, capacity: int, refill_per_second: float, clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = capacity
        self._rate = refill_per_second
        self._tokens = float(capacity)
        self._clock = clock
        self._last = clock()

    @property
    def tokens(self) -> float:
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(float(self._capacity), self._tokens + (now - self._last) * self._rate)
        self._last = now

    def allow(self, cost: int = 1) -> bool:
        self._refill()
        if cost <= self._tokens:
            self._tokens -= cost
            return True
        return False
