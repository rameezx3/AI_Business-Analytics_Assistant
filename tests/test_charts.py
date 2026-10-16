"""
tests/test_charts.py

WHY THIS FILE EXISTS:
    Confirms every ChartBuilder method produces a valid, non-empty
    Plotly figure - catching the kind of thing that only shows up when
    a chart is actually rendered (wrong column reference, empty trace,
    a theme setting that only one chart type accepts).

    Run manually:  python tests/test_charts.py
    Or via pytest: pytest tests/test_charts.py -v
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from services.charts import THEME, ChartBuilder  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

TREND_DF = pd.DataFrame({"month": pd.date_range("2018-01-01", periods=6, freq="MS"), "orders": [10, 15, 12, 20, 18, 25]})
CATEGORY_DF = pd.DataFrame({"category": ["beauty", "electronics", "toys", "books"], "revenue": [500.0, 1200.0, 300.0, 150.0]})
STATUS_DF = pd.DataFrame({"status": ["delivered", "shipped", "canceled"], "count": [900, 50, 20]})
SCATTER_DF = pd.DataFrame({"price": [10, 50, 100, 200], "review_score": [5, 4, 3, 2]})
CORR_MATRIX = pd.DataFrame(
    [[1.0, 0.4, -0.2], [0.4, 1.0, 0.1], [-0.2, 0.1, 1.0]],
    columns=["price", "freight", "review"], index=["price", "freight", "review"],
)


def _assert_valid_figure(fig: go.Figure) -> None:
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0, "Figure has no traces - would render blank."
    assert fig.layout.title.text, "Figure has no title."


def test_line_chart() -> None:
    _assert_valid_figure(ChartBuilder.line(TREND_DF, "month", "orders", "Monthly Orders"))


def test_multi_line_chart() -> None:
    df = TREND_DF.copy()
    df["revenue"] = df["orders"] * 100
    fig = ChartBuilder.multi_line(df, "month", ["orders", "revenue"], "Orders & Revenue")
    _assert_valid_figure(fig)
    assert len(fig.data) == 2, "multi_line should produce one trace per y-column."


def test_bar_chart() -> None:
    _assert_valid_figure(ChartBuilder.bar(STATUS_DF, "status", "count", "Orders by Status"))


def test_stacked_bar_chart() -> None:
    df = pd.DataFrame({"month": ["Jan", "Feb"], "new": [10, 20], "returning": [2, 5]})
    fig = ChartBuilder.stacked_bar(df, "month", ["new", "returning"], "New vs Returning")
    _assert_valid_figure(fig)
    assert len(fig.data) == 2, "one trace per column"
    assert fig.layout.barmode == "stack"
    assert [t.name for t in fig.data] == ["New", "Returning"]


def test_horizontal_bar_respects_top_n() -> None:
    fig = ChartBuilder.horizontal_bar(CATEGORY_DF, "category", "revenue", "Top Categories", top_n=2)
    _assert_valid_figure(fig)
    assert len(fig.data[0].x) == 2, "top_n=2 should limit to 2 bars."


def test_pie_chart() -> None:
    _assert_valid_figure(ChartBuilder.pie(STATUS_DF, "status", "count", "Status Mix"))


def test_funnel_chart() -> None:
    fig = ChartBuilder.funnel(["Created", "Approved", "Delivered"], [1000, 950, 900], "Order Funnel")
    _assert_valid_figure(fig)


def test_heatmap() -> None:
    _assert_valid_figure(ChartBuilder.heatmap(CORR_MATRIX, "Correlation Matrix"))


def test_heatmap_supports_count_data_without_changing_correlation_defaults() -> None:
    """Counts: sequential scale, no per-cell text, free range. Correlation defaults must be unchanged."""
    counts = pd.DataFrame([[0, 50, 400], [10, 700, 20]], columns=["a", "b", "c"], index=["x", "y"])
    fig = ChartBuilder.heatmap(counts, "Counts", zmin=None, zmax=None, color_scale="Blues", show_values=False)
    _assert_valid_figure(fig)
    assert fig.data[0].texttemplate is None
    assert fig.layout.coloraxis.cmin is None and fig.layout.coloraxis.cmax is None
    assert fig.data[0].z[1][1] == 700

    corr = ChartBuilder.heatmap(CORR_MATRIX, "Corr")
    assert corr.layout.coloraxis.cmin == -1 and corr.layout.coloraxis.cmax == 1
    assert corr.data[0].texttemplate == "%{z:.2f}"


def test_scatter_chart() -> None:
    _assert_valid_figure(ChartBuilder.scatter(SCATTER_DF, "price", "review_score", "Price vs. Review"))


def test_histogram() -> None:
    df = pd.DataFrame({"price": [10, 20, 20, 30, 30, 30, 1000]})
    _assert_valid_figure(ChartBuilder.histogram(df, "price", "Price Distribution", log_x=True))


def test_histogram_bins_account_for_every_row() -> None:
    """Pre-binning must not lose or double-count data: bar heights sum to the row count."""
    df = pd.DataFrame({"price": [5, 10, 10, 20, 50, 50, 50, 100, 500, 1000]})
    for log_x in (False, True):
        fig = ChartBuilder.histogram(df, "price", "T", nbins=8, log_x=log_x)
        assert int(sum(fig.data[0].y)) == len(df), f"log_x={log_x}: bin counts don't sum to row count"


def test_histogram_payload_does_not_grow_with_row_count() -> None:
    """
    Regression guard: px.histogram shipped every raw row to the browser
    (~1.2 MB for 112k real prices). Pre-binned output must stay small
    and roughly constant regardless of how many rows go in.
    """
    import numpy as np

    rng = np.random.default_rng(0)
    small = pd.DataFrame({"v": rng.lognormal(4, 1, 1_000)})
    large = pd.DataFrame({"v": rng.lognormal(4, 1, 200_000)})
    size_small = len(ChartBuilder.histogram(small, "v", "T", log_x=True).to_json())
    size_large = len(ChartBuilder.histogram(large, "v", "T", log_x=True).to_json())
    assert size_large < 30_000, f"histogram JSON is {size_large:,} bytes for 200k rows"
    assert size_large < size_small * 2, "payload should not scale with row count"


def test_histogram_log_scale_drops_non_positive_and_rejects_empty() -> None:
    """log_x can't plot values <= 0: they're dropped; if nothing is left, fail loudly."""
    df = pd.DataFrame({"v": [-5, 0, 10, 100, 1000]})
    fig = ChartBuilder.histogram(df, "v", "T", nbins=4, log_x=True)
    assert int(sum(fig.data[0].y)) == 3

    try:
        ChartBuilder.histogram(pd.DataFrame({"v": [-1, 0]}), "v", "T", log_x=True)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when no positive values remain for a log histogram")


def test_all_charts_share_the_same_theme() -> None:
    """
    Every chart type must carry the shared font and colour palette.

    An earlier version of this test used an `or` condition whose first
    half (template.layout.font is not None) is true even for a plain,
    unthemed Plotly figure, so it could never fail. It now asserts the
    actual THEME values, and covers every chart type, not just three.
    """
    df_multi = TREND_DF.assign(revenue=TREND_DF["orders"] * 10)
    figs = {
        "line": ChartBuilder.line(TREND_DF, "month", "orders", "T"),
        "multi_line": ChartBuilder.multi_line(df_multi, "month", ["orders", "revenue"], "T"),
        "bar": ChartBuilder.bar(STATUS_DF, "status", "count", "T"),
        "stacked_bar": ChartBuilder.stacked_bar(STATUS_DF.assign(extra=1), "status", ["count", "extra"], "T"),
        "horizontal_bar": ChartBuilder.horizontal_bar(CATEGORY_DF, "category", "revenue", "T"),
        "pie": ChartBuilder.pie(STATUS_DF, "status", "count", "T"),
        "funnel": ChartBuilder.funnel(["A", "B"], [100, 50], "T"),
        "heatmap": ChartBuilder.heatmap(CORR_MATRIX, "T"),
        "scatter": ChartBuilder.scatter(SCATTER_DF, "price", "review_score", "T"),
        "histogram": ChartBuilder.histogram(pd.DataFrame({"x": [1, 2, 3]}), "x", "T"),
    }
    for name, fig in figs.items():
        assert fig.layout.font.family == THEME["font_family"], f"{name}: wrong font"
        assert tuple(fig.layout.colorway) == tuple(THEME["colorway"]), f"{name}: wrong colorway"


if __name__ == "__main__":
    logger.info("Running standalone chart builder check...")

    checks = [
        ("line", lambda: ChartBuilder.line(TREND_DF, "month", "orders", "T")),
        ("multi_line", lambda: ChartBuilder.multi_line(TREND_DF.assign(revenue=TREND_DF["orders"] * 10), "month", ["orders", "revenue"], "T")),
        ("bar", lambda: ChartBuilder.bar(STATUS_DF, "status", "count", "T")),
        ("horizontal_bar", lambda: ChartBuilder.horizontal_bar(CATEGORY_DF, "category", "revenue", "T")),
        ("pie", lambda: ChartBuilder.pie(STATUS_DF, "status", "count", "T")),
        ("funnel", lambda: ChartBuilder.funnel(["A", "B"], [100, 50], "T")),
        ("heatmap", lambda: ChartBuilder.heatmap(CORR_MATRIX, "T")),
        ("scatter", lambda: ChartBuilder.scatter(SCATTER_DF, "price", "review_score", "T")),
        ("histogram", lambda: ChartBuilder.histogram(pd.DataFrame({"x": [1, 2, 3]}), "x", "T")),
    ]

    all_ok = True
    for name, fn in checks:
        try:
            fig = fn()
            _assert_valid_figure(fig)
            print(f"[OK]   {name}")
        except Exception as exc:
            all_ok = False
            print(f"[FAIL] {name}: {exc}")

    print("\nSUCCESS: all chart types produce valid figures." if all_ok else "\nFAILED: see above.")
    sys.exit(0 if all_ok else 1)
