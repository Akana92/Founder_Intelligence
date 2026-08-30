from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from io import BytesIO
import base64
import math

_MAX_STARTUP_BAR_POINTS = 12
_MAX_STARTUP_BAR_LABEL_LENGTH = 80
_MAX_STARTUP_BAR_TITLE_LENGTH = 80


def financial_trend_png_data_uri(points: Iterable[tuple[str, Decimal]]) -> str:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    labels = [label for label, _value in points]
    values = [float(value) for _label, value in points]
    fig, ax = plt.subplots(figsize=(4.8, 2.4), dpi=120)
    ax.plot(labels, values, marker="o", color="#1f5a7a", linewidth=2)
    ax.set_title("Financial Trend")
    ax.grid(True, color="#d8dde3", linewidth=0.6)
    fig.tight_layout()
    output = BytesIO()
    fig.savefig(output, format="png", metadata={"Software": "due-diligence-agent"})
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def startup_bar_chart_png_data_uri(
    title: str,
    points: Iterable[tuple[str, Decimal]],
) -> str | None:
    chart_title = title.strip()
    if not chart_title:
        raise ValueError("chart title is required")
    if len(chart_title) > _MAX_STARTUP_BAR_TITLE_LENGTH:
        raise ValueError("chart title is too long")

    normalized_points = tuple(_normalize_startup_bar_point(label, value) for label, value in points)
    if not normalized_points:
        return None
    if len(normalized_points) > _MAX_STARTUP_BAR_POINTS:
        raise ValueError("too many chart points")

    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    labels = [label for label, _value in normalized_points]
    values = [float(value) for _label, value in normalized_points]

    height = max(2.4, 0.45 * len(labels) + 1.2)
    fig, ax = plt.subplots(figsize=(5.8, height), dpi=120)
    ax.barh(labels, values, color="#2f6f8f")
    ax.invert_yaxis()
    ax.set_title(chart_title)
    ax.grid(True, axis="x", color="#d8dde3", linewidth=0.6)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    output = BytesIO()
    fig.savefig(output, format="png", metadata={"Software": "due-diligence-agent"})
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _normalize_startup_bar_point(label: str, value: Decimal) -> tuple[str, Decimal]:
    normalized_label = label.strip()
    if not normalized_label:
        raise ValueError("chart point label is required")
    if len(normalized_label) > _MAX_STARTUP_BAR_LABEL_LENGTH:
        raise ValueError("chart point label is too long")
    if not value.is_finite() or value < 0 or not math.isfinite(float(value)):
        raise ValueError("chart point value must be finite and non-negative")
    return normalized_label, value
