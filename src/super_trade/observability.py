"""Logfire observability configuration.

Call :func:`configure_logfire` once at a process entry point (not at import time).
Telemetry is only shipped to Logfire when a ``LOGFIRE_TOKEN`` is present, so local,
CI, and offline runs work without any setup.
"""

from __future__ import annotations

import logfire


def configure_logfire(*, console: bool = True) -> None:
    """Configure Logfire for this process."""
    kwargs: dict[str, object] = {} if console else {"console": False}
    logfire.configure(
        service_name="super-trade",
        send_to_logfire="if-token-present",
        **kwargs,
    )
