"""Unit tests for QMT symbol mapping (pure helpers — no xtquant/MiniQMT needed)."""

from __future__ import annotations

import pytest

from super_trade.sources.qmt_source import from_qmt_symbol, to_qmt_symbol


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("600519", "600519.SH"),  # Shanghai main board
        ("688981", "688981.SH"),  # STAR market (科创板)
        ("000001", "000001.SZ"),  # Shenzhen main board
        ("002594", "002594.SZ"),  # Shenzhen SME
        ("300750", "300750.SZ"),  # ChiNext (创业板)
        ("830799", "830799.BJ"),  # Beijing
        ("430047", "430047.BJ"),  # Beijing
    ],
)
def test_to_qmt_symbol(code: str, expected: str) -> None:
    assert to_qmt_symbol(code) == expected


def test_to_qmt_symbol_passthrough_when_suffixed() -> None:
    assert to_qmt_symbol("600519.SH") == "600519.SH"
    assert to_qmt_symbol("600519.sh") == "600519.SH"


def test_from_qmt_symbol() -> None:
    assert from_qmt_symbol("600519.SH") == "600519"
    assert from_qmt_symbol("000001.SZ") == "000001"


def test_round_trip() -> None:
    for code in ("600519", "000001", "300750", "830799", "688981"):
        assert from_qmt_symbol(to_qmt_symbol(code)) == code
