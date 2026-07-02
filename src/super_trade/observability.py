"""Logfire observability configuration.

Call :func:`configure_logfire` once at a process entry point (not at import time).
Telemetry is only shipped to Logfire when a ``LOGFIRE_TOKEN`` is present, so local,
CI, and offline runs work without any setup.
"""

from __future__ import annotations

import logfire


def configure_logfire(*, console: bool = True) -> None:
    """Configure Logfire for this process."""
    logfire.configure(
        service_name="super-trade",
        send_to_logfire="if-token-present",
        # ``False`` disables the console exporter; ``None`` keeps the default.
        console=None if console else False,
    )
