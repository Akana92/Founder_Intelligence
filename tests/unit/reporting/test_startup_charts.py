from __future__ import annotations

import base64
from decimal import Decimal

import pytest

from due_diligence_agent.adapters.reports.charts import startup_bar_chart_png_data_uri


def _decode_png(data_uri: str) -> bytes:
    prefix = "data:image/png;base64,"
    assert data_uri.startswith(prefix)
    return base64.b64decode(data_uri.removeprefix(prefix))


def test_startup_bar_png_data_uri_returns_deterministic_png() -> None:
    points = (
        ("TAM", Decimal("1200000000")),
        ("SAM", Decimal("260000000")),
        ("SOM", Decimal("18000000")),
    )

    first = startup_bar_chart_png_data_uri("Market Sizing", points)
    second = startup_bar_chart_png_data_uri("Market Sizing", points)

    assert first == second
    assert _decode_png(first).startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    ("title", "points"),
    [
        ("", (("TAM", Decimal("1")),)),
        ("x" * 81, (("TAM", Decimal("1")),)),
        ("Market Sizing", (("", Decimal("1")),)),
        ("Market Sizing", (("TAM", Decimal("-1")),)),
        ("Market Sizing", (("TAM", Decimal("1e10000")),)),
        ("Market Sizing", tuple((f"Metric {index}", Decimal(index)) for index in range(13))),
    ],
)
def test_startup_bar_png_data_uri_rejects_unusable_inputs(
    title: str,
    points: tuple[tuple[str, Decimal], ...],
) -> None:
    with pytest.raises(ValueError):
        startup_bar_chart_png_data_uri(title, points)


def test_startup_bar_chart_png_data_uri_returns_none_for_empty_valid_points() -> None:
    assert startup_bar_chart_png_data_uri("Market Sizing", ()) is None
