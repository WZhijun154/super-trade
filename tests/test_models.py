"""Unit tests for Pydantic models (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from super_trade.data import Bar, Interval


def _kwargs(**overrides: Any) -> dict[str, Any]:
    base = dict(
        symbol="X",
        interval=Interval.DAY,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=100,
    )
    base.update(overrides)
    return base


def test_valid_bar() -> None:
    bar = Bar(**_kwargs())
    assert bar.interval is Interval.DAY
    assert bar.interval.value == "1d"


def test_bar_is_frozen() -> None:
    bar = Bar(**_kwargs())
    with pytest.raises(ValidationError):
        bar.close = 12.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": 8.0},  # high < low
        {"volume": -1},  # negative volume
        {"open": 100.0},  # open outside [low, high]
        {"close": 100.0},  # close outside [low, high]
    ],
)
def test_invalid_bar_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Bar(**_kwargs(**overrides))
