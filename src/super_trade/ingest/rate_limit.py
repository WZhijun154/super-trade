"""Single-process rate limiting for outbound data-source requests.

eastmoney/akshare throttle per source IP and drop connections under bursts, so we
space successive calls by a minimum interval. Intentionally simple and not
thread-safe — this is the single-node, single-process tier. A distributed,
per-egress-IP limiter is the multi-node upgrade path.
"""

from __future__ import annotations

import time


class RateLimiter:
    """Block until at least ``min_interval`` seconds have passed since the last call."""

    def __init__(self, min_interval: float = 0.5) -> None:
        self._min_interval = max(0.0, min_interval)
        self._last: float | None = None

    def wait(self) -> None:
        """Sleep just long enough to honour the configured minimum interval."""
        if self._min_interval == 0.0:
            return
        now = time.monotonic()
        if self._last is not None:
            remaining = self._min_interval - (now - self._last)
            if remaining > 0:
                time.sleep(remaining)
        self._last = time.monotonic()
