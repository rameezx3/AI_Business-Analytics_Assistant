"""
services/kpi.py

WHY THIS FILE EXISTS:
    Module 8: formal, reusable KPI calculations. Module 7's Home page
    had its own inline SQL for a handful of numbers - that breaks the
    project's own architecture rule (dashboard/ is presentation only;
    business logic belongs in services/) and doesn't scale: every future
    page that needs "average order value" or "repeat customer rate"
    would otherwise reinvent the query, and could easily get the
    definition subtly wrong (e.g. counting customer_id instead of
    customer_unique_id for a "unique customers" KPI - see below).

    Every KPI here has a documented formula and was checked against the
    live database before being finalized.

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/kpi.py

USAGE:
    python services/kpi.py                    # all-time KPIs
    python services/kpi.py --days 30           # last 30 days vs. previous 30 days
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from database.connection import db
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class KPISet:
    """
    One period's worth of KPIs. Every field has a precise, documented
    definition (see KPICalculator.calculate() for the SQL behind each).
    """
    period_label: str
    total_revenue: float
    total_orders: int
    unique_customers: int
    average_order_value: float
    average_review_score: float
    fulfillment_rate_pct: float
    average_delivery_days: float
    repeat_customer_rate_pct: float
    cancellation_rate_pct: float


class KPICalculator:
    """
    Computes the project's standard KPI set, optionally scoped to a
    date range (by order_purchase_timestamp). Every KPI is a plain,
    stateless query - no hidden caching here, since Streamlit's
    @st.cache_data at the dashboard layer already handles that; this
    class stays reusable outside a Streamlit context too (e.g. for
    Module 21's PDF reports).
    """

    def __init__(self) -> None:
        self.engine = db.engine

    def calculate(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period_label: str = "All Time",
    ) -> KPISet:
        """
        Computes every KPI for the given date range (inclusive of
        start_date, exclusive of end_date + 1 day - i.e. end_date is
        the last day INCLUDED). Pass no dates for all-time KPIs.

        WHY EACH FORMULA IS WHAT IT IS:
            - total_revenue: SUM(order_items.price) for orders purchased
              in range. Deliberately excludes freight_value - "revenue"
              here means product sales, not what the customer paid
              including shipping (freight largely passes through to
              carriers, not the business's own revenue).
            - unique_customers: COUNT(DISTINCT customer_unique_id), NOT
              customer_id. Verified directly against the data: the same
              real person can have multiple customer_id values (one per
              order), so counting customer_id would overstate the
              number of actual people by counting repeat customers
              multiple times.
            - average_order_value: total_revenue / (number of orders that
              contain at least one item). Uses revenue (not revenue+
              freight) for the same reason as above. The denominator is
              deliberately NOT total_orders: 775 orders (cancelled or
              unavailable) have no items and therefore zero revenue;
              counting them would dilute the average (R$136.68 instead of
              the correct R$137.75). An earlier version of this module
              divided by all orders - corrected during Module 11, when
              Sales Analytics needed the same figure.
            - fulfillment_rate_pct: % of orders with status='delivered'.
              Verified: currently 97.0% on the full dataset.
            - repeat_customer_rate_pct: % of unique customers
              (by customer_unique_id) who placed more than one order.
              Verified: 2,997 of 96,096 = 3.1% on the full dataset -
              consistent with Olist's known one-time-buyer-heavy profile.
            - cancellation_rate_pct: % of orders with status='canceled'.
              Verified: 625 of 99,441 = 0.63% on the full dataset.
        """
        date_filter = ""
        params = {}
        if start_date is not None:
            date_filter += " AND o.order_purchase_timestamp >= :start_date"
            params["start_date"] = start_date
        if end_date is not None:
            date_filter += " AND o.order_purchase_timestamp < :end_date_exclusive"
            params["end_date_exclusive"] = end_date + timedelta(days=1)

        with self.engine.connect() as conn:
            # WHY REVENUE AND REVIEW SCORE ARE COMPUTED IN SEPARATE
            # SUBQUERIES, NOT ONE JOINED QUERY:
            # A real bug was found during testing: joining orders to
            # BOTH order_items (many rows per order) AND order_reviews
            # (also many rows per order - some orders genuinely have up
            # to 3 reviews, verified directly) in a single query creates
            # a fan-out. If an order has 3 items and 2 reviews, that
            # join produces 3x2=6 rows, and SUM(price) then counts each
            # item's price twice - inflating total revenue by about
            # 0.4% on this dataset (13.65M vs. the correct 13.59M).
            # Aggregating each one-to-many relationship independently
            # avoids this entirely.
            core = conn.execute(text(f"""
                SELECT
                    COUNT(DISTINCT o.order_id) AS total_orders,
                    COUNT(DISTINCT c.customer_unique_id) AS unique_customers,
                    (COUNT(DISTINCT o.order_id) FILTER (WHERE o.order_status = 'delivered')::numeric
                        / NULLIF(COUNT(DISTINCT o.order_id), 0) * 100) AS fulfillment_rate_pct,
                    (COUNT(DISTINCT o.order_id) FILTER (WHERE o.order_status = 'canceled')::numeric
                        / NULLIF(COUNT(DISTINCT o.order_id), 0) * 100) AS cancellation_rate_pct
                FROM orders o
                JOIN customers c ON o.customer_id = c.customer_id
                WHERE 1=1 {date_filter}
            """), params).fetchone()

            revenue = conn.execute(text(f"""
                SELECT COALESCE(SUM(oi.price), 0) FROM order_items oi
                JOIN orders o ON oi.order_id = o.order_id
                WHERE 1=1 {date_filter}
            """), params).scalar()

            orders_with_items = conn.execute(text(f"""
                SELECT COUNT(DISTINCT oi.order_id) FROM order_items oi
                JOIN orders o ON oi.order_id = o.order_id
                WHERE 1=1 {date_filter}
            """), params).scalar()

            avg_review = conn.execute(text(f"""
                SELECT COALESCE(AVG(r.review_score), 0) FROM order_reviews r
                JOIN orders o ON r.order_id = o.order_id
                WHERE 1=1 {date_filter}
            """), params).scalar()

            avg_delivery = conn.execute(text(f"""
                SELECT AVG(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400)
                FROM orders o
                WHERE o.order_delivered_customer_date IS NOT NULL {date_filter}
            """), params).scalar()

            repeat = conn.execute(text(f"""
                SELECT
                    COUNT(*) AS unique_customers,
                    COUNT(*) FILTER (WHERE order_count > 1) AS repeat_customers
                FROM (
                    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_count
                    FROM customers c JOIN orders o ON o.customer_id = c.customer_id
                    WHERE 1=1 {date_filter}
                    GROUP BY c.customer_unique_id
                ) t
            """), params).fetchone()

        total_orders = int(core.total_orders or 0)
        total_revenue = float(revenue or 0)
        repeat_rate = (
            round(100 * repeat.repeat_customers / repeat.unique_customers, 2)
            if repeat.unique_customers else 0.0
        )

        return KPISet(
            period_label=period_label,
            total_revenue=round(total_revenue, 2),
            total_orders=total_orders,
            unique_customers=int(core.unique_customers or 0),
            average_order_value=round(total_revenue / int(orders_with_items), 2) if orders_with_items else 0.0,
            average_review_score=round(float(avg_review or 0), 2),
            fulfillment_rate_pct=round(float(core.fulfillment_rate_pct or 0), 2),
            average_delivery_days=round(float(avg_delivery), 2) if avg_delivery is not None else 0.0,
            repeat_customer_rate_pct=repeat_rate,
            cancellation_rate_pct=round(float(core.cancellation_rate_pct or 0), 2),
        )

    def calculate_with_comparison(self, period_days: int = 30) -> dict:
        """
        Computes KPIs for the last `period_days` days AND the equal-length
        period immediately before it, plus the percent change for every
        KPI - the standard "+12% vs last period" pattern used throughout
        BI dashboards.

        WHY "TODAY" IS ANCHORED TO THE DATASET'S OWN LAST ORDER DATE:
            This dataset's most recent order is from 2018-10-17 - using
            the real current date would make "last 30 days" empty. Any
            BI tool built on a static/historical dataset needs to anchor
            "now" to the data itself, not the system clock.

        KNOWN CAVEAT WITH SHORT PERIODS NEAR THE DATASET'S END:
            Verified directly: the final 30 days of this dataset (2018-
            09-18 to 2018-10-17) contain only 8 orders, and all 8 are
            'canceled' with no items or revenue - a real characteristic
            of the source data (Olist's collection window ends before
            those orders could be fulfilled), not a bug here. This
            produces dramatic, alarming-looking deltas like "-100%
            revenue" for `--days 30`. Consistent with the sharp drop
            visible at the end of Module 6's monthly order trend chart.
            A longer period (e.g. `--days 90`) avoids landing entirely
            inside this collection-cutoff window.
        """
        with self.engine.connect() as conn:
            max_date = conn.execute(text("SELECT MAX(order_purchase_timestamp) FROM orders")).scalar()
        anchor = max_date.date()

        current_end = anchor
        current_start = anchor - timedelta(days=period_days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)

        current = self.calculate(current_start, current_end, f"Last {period_days} days")
        previous = self.calculate(previous_start, previous_end, f"Previous {period_days} days")

        def pct_change(curr: float, prev: float) -> Optional[float]:
            if prev == 0:
                return None
            return round(100 * (curr - prev) / prev, 1)

        deltas = {
            field: pct_change(getattr(current, field), getattr(previous, field))
            for field in [
                "total_revenue", "total_orders", "unique_customers", "average_order_value",
                "average_review_score", "fulfillment_rate_pct", "average_delivery_days",
                "repeat_customer_rate_pct", "cancellation_rate_pct",
            ]
        }

        return {"current": current, "previous": previous, "pct_change": deltas}


def main() -> None:
    """CLI entry point: `python services/kpi.py [--days N]`."""
    parser = argparse.ArgumentParser(description="Calculate business KPIs.")
    parser.add_argument("--days", type=int, default=None, help="Compare last N days vs. previous N days.")
    args = parser.parse_args()

    if not db.test_connection():
        print("Cannot calculate KPIs - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    calculator = KPICalculator()

    if args.days:
        result = calculator.calculate_with_comparison(args.days)
        print(f"\n=== {result['current'].period_label} vs. {result['previous'].period_label} ===")
        for field in result["pct_change"]:
            curr = getattr(result["current"], field)
            change = result["pct_change"][field]
            change_str = f"{change:+.1f}%" if change is not None else "n/a"
            print(f"  {field}: {curr}  ({change_str})")
    else:
        kpis = calculator.calculate()
        print(f"\n=== {kpis.period_label} KPIs ===")
        for field, value in kpis.__dict__.items():
            if field != "period_label":
                print(f"  {field}: {value}")


if __name__ == "__main__":
    main()
