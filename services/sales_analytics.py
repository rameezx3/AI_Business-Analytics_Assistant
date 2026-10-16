"""
services/sales_analytics.py

WHY THIS FILE EXISTS:
    Module 11: sales analytics - how much is sold, how sales trend over
    time, where they come from (category, state), how customers pay, and
    when they buy. Business logic lives here; dashboard/sales.py only
    presents it.

    Every definition was chosen after profiling the real data. The
    findings that shaped the design:

    1. GROSS SALES = SUM(order_items.price) over ALL orders - the same
       definition as Module 8's total_revenue, so the two reconcile.
       97.3% of it sits in delivered orders; the rest is in cancelled,
       unavailable, or still-in-progress orders, so those slices are
       reported separately instead of being hidden inside one number.
    2. THE TIMELINE HAS A HOLE AND UNRELIABLE EDGES. November 2016 has
       no orders at all, and Sep/Oct/Dec 2016 and Sep/Oct 2018 have
       almost none (collection ramp-up and cutoff). The monthly series
       is therefore reindexed to EVERY calendar month, and growth rates
       are only computed between months that pass a stated reliability
       rule - otherwise "December 2016 vs November 2016" would be
       computed against a month that does not exist.
    3. PAYMENTS != SALES. Total payments exceed items + freight by
       R$165k (1.0%). Measured breakdown: R$162k was paid on cancelled/
       unavailable/new orders that have NO items at all, and the small
       remainder is delivered orders overpaid by credit-card
       installments (226 of 229 overpaid orders used multi-installment
       cards). So payment amounts are labelled "money paid" (including
       shipping and interest), never presented as revenue.

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/sales_analytics.py

USAGE:
    python services/sales_analytics.py
"""

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import text

from database.connection import db
from utils.logger import get_logger

logger = get_logger(__name__)

# A month counts as "reliable" for growth comparisons if at least this
# many orders were placed in it. On the real data this separates the 20
# genuine trading months (Jan 2017 - Aug 2018, each 800+ orders) from the
# 5 ramp-up / cutoff months (each under 330 orders, some with 1-16).
MIN_RELIABLE_MONTH_ORDERS = 500

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# PostgreSQL EXTRACT(DOW): 0 = Sunday ... 6 = Saturday
_DOW_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
              5: "Friday", 6: "Saturday", 0: "Sunday"}


@dataclass
class SalesSummary:
    """Headline sales numbers. Plain Python int/float/str/None only (JSON-safe)."""
    gross_sales: float
    delivered_sales: float
    canceled_sales: float          # status canceled + unavailable
    in_progress_sales: float       # every other non-delivered status
    delivered_share_pct: float
    sales_orders: int              # orders containing at least one item
    items_sold: int
    avg_order_value: float
    avg_items_per_order: float
    freight_total: float
    freight_pct_of_sales: float
    payments_total: float
    payments_on_orders_without_items: float
    reliable_months: int
    reliable_window_start: str
    reliable_window_end: str
    best_month: str
    best_month_sales: float
    best_month_mom_growth_pct: Optional[float]
    yoy_growth_pct: Optional[float]
    yoy_months_compared: int


class SalesAnalytics:
    """Stateless query layer: every method returns plain DataFrames/dicts ready for charting."""

    def __init__(self) -> None:
        self.engine = db.engine

    # ------------------------------------------------------------------ trend

    def monthly_sales(self, min_orders: int = MIN_RELIABLE_MONTH_ORDERS) -> pd.DataFrame:
        """
        One row per CALENDAR month from the first to the last month in the
        data - including months with no orders (November 2016), which
        appear with zeros instead of silently vanishing.

        Columns: month, orders_placed (any status), sales_orders (orders
        with items), items, gross_sales, delivered_sales, freight,
        avg_order_value, reliable, mom_growth_pct, yoy_growth_pct.

        Growth is only computed when BOTH months being compared are
        reliable (>= min_orders orders placed); otherwise it is NaN.
        mom_growth_pct compares with the previous calendar month,
        yoy_growth_pct with the same month a year earlier.

        WHY ORDERS AND SALES ARE AGGREGATED IN SEPARATE SUBQUERIES:
            orders_placed counts every order; the sales figures join
            order_items (many rows per order). Doing both in one joined
            query would count an order once per item.
        """
        raw = pd.read_sql(
            """
            WITH placed AS (
                SELECT DATE_TRUNC('month', order_purchase_timestamp) AS month,
                       COUNT(*) AS orders_placed
                FROM orders GROUP BY 1
            ),
            sold AS (
                SELECT DATE_TRUNC('month', o.order_purchase_timestamp) AS month,
                       COUNT(DISTINCT oi.order_id) AS sales_orders,
                       COUNT(*) AS items,
                       SUM(oi.price) AS gross_sales,
                       SUM(oi.price) FILTER (WHERE o.order_status = 'delivered') AS delivered_sales,
                       SUM(oi.freight_value) AS freight
                FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
                GROUP BY 1
            )
            SELECT p.month, p.orders_placed,
                   s.sales_orders, s.items, s.gross_sales, s.delivered_sales, s.freight
            FROM placed p LEFT JOIN sold s ON s.month = p.month
            ORDER BY p.month
            """,
            self.engine,
        )
        raw["month"] = pd.to_datetime(raw["month"])
        full_range = pd.date_range(raw["month"].min(), raw["month"].max(), freq="MS")
        df = raw.set_index("month").reindex(full_range)
        df.index.name = "month"

        for col in ["orders_placed", "sales_orders", "items"]:
            df[col] = df[col].fillna(0).astype("int64")
        for col in ["gross_sales", "delivered_sales", "freight"]:
            df[col] = df[col].fillna(0.0).astype(float).round(2)
        df = df.reset_index()

        df["avg_order_value"] = (df["gross_sales"] / df["sales_orders"].where(df["sales_orders"] > 0)).round(2)
        df["reliable"] = df["orders_placed"] >= min_orders

        for lag, name in [(1, "mom_growth_pct"), (12, "yoy_growth_pct")]:
            prior = df["gross_sales"].shift(lag)
            prior_ok = df["reliable"].shift(lag, fill_value=False).astype(bool)
            comparable = df["reliable"] & prior_ok & (prior > 0)
            df[name] = (((df["gross_sales"] / prior) - 1) * 100).where(comparable).round(1)
        return df

    def reliable_window(
        self,
        min_orders: int = MIN_RELIABLE_MONTH_ORDERS,
        monthly: Optional[pd.DataFrame] = None,
    ) -> Tuple[date, date]:
        """(first day, last day) spanned by the reliable months."""
        m = monthly if monthly is not None else self.monthly_sales(min_orders)
        rel = m.loc[m["reliable"], "month"]
        start = rel.min()
        end = rel.max() + pd.offsets.MonthEnd(0)
        return start.date(), end.date()

    def daily_sales(self, start: date, end: date) -> pd.DataFrame:
        """
        One row per calendar DAY in [start, end] inclusive, with zeros for
        days without sales. Columns: day, sales_orders, gross_sales.
        """
        # Bound with text() and :name placeholders - pg8000 rejects the
        # %(name)s style that pandas would otherwise pass through.
        raw = pd.read_sql(
            text("""
                SELECT o.order_purchase_timestamp::date AS day,
                       COUNT(DISTINCT oi.order_id) AS sales_orders,
                       SUM(oi.price) AS gross_sales
                FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
                WHERE o.order_purchase_timestamp >= :start
                  AND o.order_purchase_timestamp <  :end_excl
                GROUP BY 1 ORDER BY 1
            """),
            self.engine,
            params={"start": start, "end_excl": (pd.Timestamp(end) + pd.Timedelta(days=1)).to_pydatetime()},
        )
        raw["day"] = pd.to_datetime(raw["day"])
        df = raw.set_index("day").reindex(pd.date_range(start, end, freq="D"))
        df.index.name = "day"
        df["sales_orders"] = df["sales_orders"].fillna(0).astype("int64")
        df["gross_sales"] = df["gross_sales"].fillna(0.0).astype(float).round(2)
        return df.reset_index()

    def top_days(self, n: int = 5) -> pd.DataFrame:
        """The n highest-selling calendar days."""
        df = pd.read_sql(
            text("""
                SELECT o.order_purchase_timestamp::date AS day,
                       COUNT(DISTINCT oi.order_id) AS sales_orders,
                       SUM(oi.price) AS gross_sales
                FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
                GROUP BY 1 ORDER BY gross_sales DESC, day LIMIT :n
            """),
            self.engine, params={"n": int(n)},
        )
        df["day"] = pd.to_datetime(df["day"])
        df["gross_sales"] = df["gross_sales"].astype(float).round(2)
        return df

    # --------------------------------------------------------------- headline

    def summary(self) -> SalesSummary:
        """Headline numbers; see the module docstring for why each slice exists."""
        with self.engine.connect() as conn:
            r = conn.execute(text("""
                SELECT SUM(oi.price) AS gross,
                       SUM(oi.price) FILTER (WHERE o.order_status = 'delivered') AS delivered,
                       SUM(oi.price) FILTER (WHERE o.order_status IN ('canceled', 'unavailable')) AS canceled,
                       SUM(oi.freight_value) AS freight,
                       COUNT(DISTINCT oi.order_id) AS sales_orders,
                       COUNT(*) AS items
                FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
            """)).fetchone()
            pay = conn.execute(text("""
                SELECT SUM(p.payment_value) AS total,
                       SUM(p.payment_value) FILTER (
                           WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = p.order_id)
                       ) AS without_items
                FROM order_payments p
            """)).fetchone()

        gross = float(r.gross or 0)
        delivered = float(r.delivered or 0)
        canceled = float(r.canceled or 0)
        sales_orders = int(r.sales_orders or 0)

        m = self.monthly_sales()
        rel = m[m["reliable"]]
        best = rel.loc[rel["gross_sales"].idxmax()]

        # Year-over-year over the months where BOTH years are reliable:
        # compare the same set of months in each year so partial years
        # can't distort the result.
        comparable = m[m["yoy_growth_pct"].notna()]
        if len(comparable):
            current = float(comparable["gross_sales"].sum())
            prior = float(m["gross_sales"].shift(12)[comparable.index].sum())
            yoy: Optional[float] = round(100 * (current / prior - 1), 1)
        else:
            yoy = None

        mom = best["mom_growth_pct"]
        return SalesSummary(
            gross_sales=round(gross, 2),
            delivered_sales=round(delivered, 2),
            canceled_sales=round(canceled, 2),
            in_progress_sales=round(gross - delivered - canceled, 2),
            delivered_share_pct=round(100 * delivered / gross, 2) if gross else 0.0,
            sales_orders=sales_orders,
            items_sold=int(r.items or 0),
            avg_order_value=round(gross / sales_orders, 2) if sales_orders else 0.0,
            avg_items_per_order=round(float(r.items) / sales_orders, 2) if sales_orders else 0.0,
            freight_total=round(float(r.freight or 0), 2),
            freight_pct_of_sales=round(100 * float(r.freight or 0) / gross, 2) if gross else 0.0,
            payments_total=round(float(pay.total or 0), 2),
            payments_on_orders_without_items=round(float(pay.without_items or 0), 2),
            reliable_months=int(len(rel)),
            reliable_window_start=rel["month"].min().strftime("%Y-%m"),
            reliable_window_end=rel["month"].max().strftime("%Y-%m"),
            best_month=best["month"].strftime("%Y-%m"),
            best_month_sales=round(float(best["gross_sales"]), 2),
            best_month_mom_growth_pct=None if pd.isna(mom) else float(mom),
            yoy_growth_pct=yoy,
            yoy_months_compared=int(len(comparable)),
        )

    # ------------------------------------------------------------- breakdowns

    def sales_by_category(self, top_n: Optional[int] = None) -> pd.DataFrame:
        """
        Gross sales by product category (English names).

        COALESCE(english, portuguese, 'unknown') means products with no
        category - which exist in the raw data and are labelled 'unknown'
        by Module 4's cleaning - land in the SAME 'unknown' bucket whether
        or not cleaning has run, so category totals always add up to
        gross sales. `orders` counts orders CONTAINING the category, so it
        can legitimately sum to more than the number of orders.
        """
        df = pd.read_sql(
            """
            SELECT COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
                   SUM(oi.price) AS gross_sales,
                   COUNT(*) AS units,
                   COUNT(DISTINCT oi.order_id) AS orders,
                   AVG(oi.price) AS avg_price
            FROM order_items oi
            JOIN products p ON p.product_id = oi.product_id
            LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
            GROUP BY 1
            ORDER BY gross_sales DESC, category
            """,
            self.engine,
        )
        df["pct_of_sales"] = (100 * df["gross_sales"] / df["gross_sales"].sum()).round(2)
        df["gross_sales"] = df["gross_sales"].astype(float).round(2)
        df["avg_price"] = df["avg_price"].astype(float).round(2)
        return df.head(top_n).reset_index(drop=True) if top_n else df

    def sales_by_state(self) -> pd.DataFrame:
        """
        Gross sales by the state the ORDER was placed from. Uses the
        order's own customer record (customer_id is per order), so unlike
        Module 10's per-person view there is no 'person who moved' issue.
        freight_pct is shipping cost as a share of item sales - high for
        distant states.
        """
        df = pd.read_sql(
            """
            SELECT c.customer_state AS state,
                   SUM(oi.price) AS gross_sales,
                   COUNT(DISTINCT oi.order_id) AS orders,
                   SUM(oi.freight_value) AS freight
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            JOIN customers c ON c.customer_id = o.customer_id
            GROUP BY 1
            ORDER BY gross_sales DESC
            """,
            self.engine,
        )
        df["gross_sales"] = df["gross_sales"].astype(float)
        df["freight"] = df["freight"].astype(float)
        df["pct_of_sales"] = (100 * df["gross_sales"] / df["gross_sales"].sum()).round(2)
        df["avg_order_value"] = (df["gross_sales"] / df["orders"]).round(2)
        df["freight_pct"] = (100 * df["freight"] / df["gross_sales"]).round(1)
        df["gross_sales"] = df["gross_sales"].round(2)
        df["freight"] = df["freight"].round(2)
        return df.reset_index(drop=True)

    def payment_mix(self) -> pd.DataFrame:
        """
        Money PAID by payment method. payment_value includes shipping and
        any installment interest and covers payments on orders that never
        had items (see module docstring) - so this is "money paid", not
        revenue, and its total intentionally differs from gross sales.
        """
        df = pd.read_sql(
            """
            SELECT payment_type,
                   COUNT(*) AS payments,
                   SUM(payment_value) AS payment_value,
                   AVG(payment_installments) AS avg_installments
            FROM order_payments GROUP BY payment_type ORDER BY payment_value DESC
            """,
            self.engine,
        )
        df["payment_value"] = df["payment_value"].astype(float)
        df["pct_of_value"] = (100 * df["payment_value"] / df["payment_value"].sum()).round(2)
        df["payment_value"] = df["payment_value"].round(2)
        df["avg_installments"] = df["avg_installments"].astype(float).round(2)
        return df

    def credit_card_installments(self) -> pd.DataFrame:
        """
        Credit-card payments grouped by number of installments. The 2
        payments recorded with 0 installments (flagged by Module 5's
        validation) are grouped with '1x'.
        """
        df = pd.read_sql(
            """
            SELECT CASE WHEN payment_installments <= 1 THEN '1x'
                        WHEN payment_installments <= 3 THEN '2-3x'
                        WHEN payment_installments <= 6 THEN '4-6x'
                        WHEN payment_installments <= 10 THEN '7-10x'
                        ELSE '11x+' END AS installments,
                   COUNT(*) AS payments,
                   SUM(payment_value) AS payment_value
            FROM order_payments WHERE payment_type = 'credit_card'
            GROUP BY 1
            """,
            self.engine,
        )
        order = ["1x", "2-3x", "4-6x", "7-10x", "11x+"]
        df = df.set_index("installments").reindex(order, fill_value=0).rename_axis("installments").reset_index()
        df["payments"] = df["payments"].astype("int64")
        df["payment_value"] = df["payment_value"].astype(float)
        df["avg_payment"] = (df["payment_value"] / df["payments"].where(df["payments"] > 0)).round(2)
        df["pct_of_card_value"] = (100 * df["payment_value"] / df["payment_value"].sum()).round(2)
        df["payment_value"] = df["payment_value"].round(2)
        return df

    # ---------------------------------------------------------- order values

    def order_values(self) -> pd.DataFrame:
        """One row per order that has items: order_id, order_value (sum of item prices)."""
        df = pd.read_sql(
            "SELECT order_id, SUM(price) AS order_value FROM order_items GROUP BY order_id",
            self.engine,
        )
        df["order_value"] = df["order_value"].astype(float)
        return df

    def order_value_summary(self, order_values: Optional[pd.DataFrame] = None) -> Dict[str, float]:
        """Mean, median, 90th/99th percentile and max order value."""
        values = order_values if order_values is not None else self.order_values()
        v = values["order_value"]
        return {
            "mean": round(float(v.mean()), 2),
            "median": round(float(v.median()), 2),
            "p90": round(float(v.quantile(0.90)), 2),
            "p99": round(float(v.quantile(0.99)), 2),
            "max": round(float(v.max()), 2),
        }

    # ----------------------------------------------------------- demand rhythm

    def weekday_hour_matrix(self) -> pd.DataFrame:
        """
        Orders placed by weekday (rows, Monday-Sunday) and hour (columns,
        0-23), over ALL orders. Times are as recorded in the dataset,
        which does not state a timezone.
        """
        raw = pd.read_sql(
            """
            SELECT EXTRACT(DOW FROM order_purchase_timestamp)::int AS dow,
                   EXTRACT(HOUR FROM order_purchase_timestamp)::int AS hour,
                   COUNT(*) AS orders
            FROM orders GROUP BY 1, 2
            """,
            self.engine,
        )
        raw["weekday"] = raw["dow"].map(_DOW_NAMES)
        m = raw.pivot(index="weekday", columns="hour", values="orders")
        m = m.reindex(index=WEEKDAYS, columns=list(range(24))).fillna(0).astype("int64")
        m.columns.name = "hour"
        return m

    def demand_pattern(self, matrix: Optional[pd.DataFrame] = None) -> Dict[str, object]:
        """Busiest/quietest weekday, busiest hour, weekend share - all derived from the matrix."""
        m = matrix if matrix is not None else self.weekday_hour_matrix()
        by_day = m.sum(axis=1)
        by_hour = m.sum(axis=0)
        total = int(m.to_numpy().sum())
        return {
            "busiest_weekday": str(by_day.idxmax()),
            "busiest_weekday_orders": int(by_day.max()),
            "quietest_weekday": str(by_day.idxmin()),
            "quietest_weekday_orders": int(by_day.min()),
            "busiest_hour": int(by_hour.idxmax()),
            "busiest_hour_orders": int(by_hour.max()),
            "weekend_share_pct": round(100 * float(by_day["Saturday"] + by_day["Sunday"]) / total, 1),
            "total_orders": total,
        }


def main() -> None:
    """CLI entry point: `python services/sales_analytics.py`."""
    if not db.test_connection():
        print("Cannot analyse sales - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    sa = SalesAnalytics()
    print("\n=== Sales Summary ===")
    for field, value in sa.summary().__dict__.items():
        print(f"  {field}: {value}")
    print("\n=== Top 5 categories ===")
    print(sa.sales_by_category(5).to_string(index=False))
    print("\n=== Payment mix ===")
    print(sa.payment_mix().to_string(index=False))
    print("\n=== Demand pattern ===")
    print(sa.demand_pattern())
    print("\n=== Top 5 sales days ===")
    print(sa.top_days(5).to_string(index=False))


if __name__ == "__main__":
    main()
