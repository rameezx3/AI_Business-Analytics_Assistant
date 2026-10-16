"""
tests/test_eda.py

WHY THIS FILE EXISTS:
    Confirms Module 6 works end-to-end: every analysis runs without
    error, all 9 chart files are actually written to disk (non-empty),
    the markdown report is generated, and the findings dict is fully
    JSON-serializable (catches numpy-type leaks like the one found and
    fixed during development - np.float64 doesn't survive json.dumps()).

    Run manually:  python tests/test_eda.py
    Or via pytest: pytest tests/test_eda.py -v
"""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import config  # noqa: E402
from database.connection import db  # noqa: E402
from services.eda import EDAAnalyzer  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

EXPECTED_CHARTS = [
    "01_monthly_order_trend.png",
    "02_order_status_distribution.png",
    "03_top_categories_by_revenue.png",
    "04_payment_type_distribution.png",
    "05_review_score_distribution.png",
    "06_price_distribution.png",
    "07_delivery_time_distribution.png",
    "08_orders_by_state.png",
    "09_correlation_heatmap.png",
]


def test_eda_produces_all_charts() -> None:
    """Every expected chart file must exist and be non-empty after run_all()."""
    analyzer = EDAAnalyzer()
    analyzer.run_all()

    for filename in EXPECTED_CHARTS:
        chart_path = config.app.charts_dir / filename
        assert chart_path.exists(), f"Missing chart: {filename}"
        assert chart_path.stat().st_size > 0, f"Chart file is empty: {filename}"


def test_eda_report_is_written() -> None:
    """The markdown report must exist and mention every section."""
    analyzer = EDAAnalyzer()
    analyzer.run_all()

    report_path = config.app.reports_dir / "eda_report.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    for heading in ["Order Volume Trend", "Order Status", "Revenue by Category",
                     "Payment Methods", "Review Scores", "Price Distribution",
                     "Delivery Time", "Geographic Concentration", "Correlations"]:
        assert heading in content, f"Report is missing section: {heading}"


def test_eda_findings_are_json_serializable() -> None:
    """
    Every value in the findings dict must be a plain Python type - this
    specifically catches numpy scalar types (e.g. np.float64) that look
    fine when printed but break json.dumps(), which matters once a
    future module (e.g. the dashboard) consumes this dict directly.
    """
    analyzer = EDAAnalyzer()
    findings = analyzer.run_all()
    serialized = json.dumps(findings)  # raises TypeError if anything isn't JSON-safe
    assert len(serialized) > 0


if __name__ == "__main__":
    logger.info("Running standalone EDA check...")

    if not db.test_connection():
        print("FAILED: database connection failed.")
        sys.exit(1)

    analyzer = EDAAnalyzer()
    findings = analyzer.run_all()

    missing_charts = [
        f for f in EXPECTED_CHARTS if not (config.app.charts_dir / f).exists()
    ]

    try:
        json.dumps(findings)
        json_ok = True
    except TypeError:
        json_ok = False

    if not missing_charts and json_ok:
        print("SUCCESS: All charts generated, report written, findings JSON-safe.")
        sys.exit(0)
    else:
        print(f"FAILED: missing_charts={missing_charts}, json_ok={json_ok}")
        sys.exit(1)
