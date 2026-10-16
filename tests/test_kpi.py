"""
tests/test_kpi.py

WHY THIS FILE EXISTS:
    Confirms Module 8's KPI calculations are correct against the real
    database - specifically guards against the fan-out bug found during
    development (joining order_items and order_reviews together
    inflated total_revenue by ~0.4%, since some orders have up to 3
    reviews). total_revenue is checked against a raw, independently
    computed SUM() query as the source of truth.

    Run manually:  python tests/test_kpi.py
    Or via pytest: pytest tests/test_kpi.py -v
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from database.connection import db  # noqa: E402
from services.kpi import KPICalculator  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def test_total_revenue_matches_raw_sum() -> None:
    """
    Guards against the fan-out bug: total_revenue must exactly match a
    plain SUM(price) query, independent of any JOIN to orders/reviews.
    """
    with db.engine.connect() as conn:
        raw_total = conn.execute(text("SELECT SUM(price) FROM order_items")).scalar()

    kpis = KPICalculator().calculate()
    assert abs(kpis.total_revenue - float(raw_total)) < 0.01, (
        f"KPI revenue {kpis.total_revenue} != raw SUM {raw_total} - possible join fan-out regression."
    )


def test_unique_customers_uses_customer_unique_id() -> None:
    """
    unique_customers must count distinct customer_unique_id, not
    customer_id - otherwise repeat customers get counted once per order.
    """
    with db.engine.connect() as conn:
        distinct_unique_id = conn.execute(
            text("SELECT COUNT(DISTINCT customer_unique_id) FROM customers")
        ).scalar()
        distinct_customer_id = conn.execute(
            text("SELECT COUNT(DISTINCT customer_id) FROM customers")
        ).scalar()

    kpis = KPICalculator().calculate()
    assert kpis.unique_customers == distinct_unique_id
    # Sanity check the two ARE different on this dataset - otherwise
    # this test wouldn't actually be testing anything meaningful.
    assert distinct_unique_id < distinct_customer_id


def test_average_order_value_excludes_orders_without_items() -> None:
    """
    AOV = revenue / orders that contain items (independent SQL), NOT
    revenue / all orders. 775 orders have no items; dividing by them
    understates AOV (136.68 vs 137.75) - a bug fixed in Module 11.
    """
    with db.engine.connect() as conn:
        revenue = float(conn.execute(text("SELECT SUM(price) FROM order_items")).scalar())
        with_items = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM order_items")).scalar()
        all_orders = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar()
    assert with_items < all_orders, "dataset has no item-less orders - test would prove nothing"

    kpis = KPICalculator().calculate()
    assert kpis.average_order_value == round(revenue / with_items, 2)
    assert kpis.average_order_value != round(revenue / all_orders, 2)


def test_rates_are_valid_percentages() -> None:
    """Fulfillment, cancellation, and repeat-customer rates must be within 0-100."""
    kpis = KPICalculator().calculate()
    for value in [kpis.fulfillment_rate_pct, kpis.cancellation_rate_pct, kpis.repeat_customer_rate_pct]:
        assert 0 <= value <= 100


def test_comparison_returns_current_and_previous() -> None:
    """calculate_with_comparison() must return both periods plus a delta for every field."""
    result = KPICalculator().calculate_with_comparison(period_days=90)
    assert "current" in result and "previous" in result and "pct_change" in result
    assert result["current"].period_label != result["previous"].period_label


if __name__ == "__main__":
    logger.info("Running standalone KPI check...")

    if not db.test_connection():
        print("FAILED: database not reachable.")
        sys.exit(1)

    calculator = KPICalculator()
    kpis = calculator.calculate()

    with db.engine.connect() as conn:
        raw_total = float(conn.execute(text("SELECT SUM(price) FROM order_items")).scalar())

    revenue_ok = abs(kpis.total_revenue - raw_total) < 0.01
    print(f"KPI total_revenue: {kpis.total_revenue}, raw SUM: {raw_total}, match: {revenue_ok}")

    if revenue_ok:
        print("SUCCESS: KPI revenue matches raw data.")
        sys.exit(0)
    else:
        print("FAILED: KPI revenue does not match raw data - check for a join fan-out.")
        sys.exit(1)
