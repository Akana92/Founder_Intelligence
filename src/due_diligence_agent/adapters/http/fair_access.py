from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
import asyncio
import time


Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class FairAccessLimiter:
    def __init__(
        self,
        *,
        max_requests_per_second: int = 10,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        if max_requests_per_second <= 0 or max_requests_per_second > 10:
            raise ValueError("max_requests_per_second must be between 1 and 10")
        self._max_requests = max_requests_per_second
        self._clock = clock
        self._sleeper = sleeper
        self._window: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._drop_expired(now)
                if len(self._window) < self._max_requests:
                    self._window.append(now)
                    return
                wait_for = max(0.0, 1.0 - (now - self._window[0]))
                await self._sleeper(wait_for)

    def _drop_expired(self, now: float) -> None:
        while self._window and now - self._window[0] >= 1.0:
            self._window.popleft()
