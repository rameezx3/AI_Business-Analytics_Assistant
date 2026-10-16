"""
services/customer_analytics.py

WHY THIS FILE EXISTS:
    Module 10: customer analytics - who the customers are, where they
    are, whether they come back, and how much they spend. Like Module 8
    (KPIs), this is business logic, so it lives in services/ and the
    dashboard page only presents it.

    Every definition below was chosen after profiling the real data
    (see each method's docstring for the numbers behind the decision).

KEY DEFINITIONS (all verified against the live database):
    - A "customer" is a customer_unique_id (a real person), never a
      customer_id (one row per ORDER). 99,441 customer_ids = 96,096 people.
    - A person's state/city is taken from their MOST RECENT order. 39
      people appear in more than one state (they moved between orders);
      using "most recent" counts each person exactly once, so per-state
      customer counts always add up to the true total.
    - Spend = SUM(order_items.price), the same definition as Module 8's
      total_revenue (excludes freight), so the two modules reconcile.

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/customer_analytics.py

USAGE:
    python services/customer_analytics.py
"""

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import text

from database.connection import db
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CustomerSummary:
    """Headline customer numbers. Every value is a plain Python int/float (JSON-safe)."""
    unique_customers: int
    paying_customers: int
    zero_spend_customers: int
    one_time_customers: int
    repeat_customers: int
    repeat_rate_pct: float
    returned_after_24h_customers: int
    returned_after_24h_rate_pct: float
    avg_orders_per_customer: float
    avg_spend: float
    median_spend: float
    p99_spend: float
    max_spend: float
    top_1pct_revenue_share_pct: float
    median_days_to_return: Optional[float]
    mean_days_to_return: Optional[float]


class CustomerAnalytics:
    """
    Builds a one-row-per-person table once (customer_table) and derives
    every metric from it, so all numbers on the customer page come from
    the same consistent snapshot.
    """

    def __init__(self) -> None:
        self.engine = db.engine
        self._table: Optional[pd.DataFrame] = None

    def customer_table(self) -> pd.DataFrame:
        """
        One row per real person (customer_unique_id), cached on the instance.

        Columns: customer_unique_id, state, city, orders, first_order,
        last_order, return_order, spend.

        return_order is the earliest order placed at least 24 hours
        AFTER the person's first order (NULL if they never did) - see
        summary() for why 24 hours is the dividing line.

        WHY SPEND IS COMPUTED IN ITS OWN CTE:
            Spend joins customers -> orders -> order_items. Order counts
            come from a separate customers -> orders pass. Mixing both
            in one join (or adding order_reviews, which has several rows
            for some orders) would multiply rows and inflate sums - the
            same fan-out bug found in Module 8.
        """
        if self._table is not None:
            return self._table

        self._table = pd.read_sql(
            """
            WITH ord AS (
                SELECT c.customer_unique_id AS uid, c.customer_state AS state, c.customer_city AS city,
                       o.order_id, o.order_purchase_timestamp AS ts,
                       MIN(o.order_purchase_timestamp) OVER (PARTITION BY c.customer_unique_id) AS first_order_ts,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.customer_unique_id
                           ORDER BY o.order_purchase_timestamp DESC, o.order_id DESC
                       ) AS recency_rank
                FROM customers c
                JOIN orders o ON o.customer_id = c.customer_id
            ),
            per_person AS (
                SELECT uid,
                       MAX(state) FILTER (WHERE recency_rank = 1) AS state,
                       MAX(city)  FILTER (WHERE recency_rank = 1) AS city,
                       COUNT(*) AS orders,
                       MIN(ts) AS first_order,
                       MAX(ts) AS last_order,
                       MIN(ts) FILTER (WHERE ts >= first_order_ts + INTERVAL '1 day') AS return_order
                FROM ord
                GROUP BY uid
            ),
            spend AS (
                SELECT c.customer_unique_id AS uid, SUM(oi.price) AS spend
                FROM customers c
                JOIN orders o ON o.customer_id = c.customer_id
                JOIN order_items oi ON oi.order_id = o.order_id
                GROUP BY c.customer_unique_id
            )
            SELECT p.uid AS customer_unique_id, p.state, p.city, p.orders,
                   p.first_order, p.last_order, p.return_order,
                   COALESCE(s.spend, 0) AS spend
            FROM per_person p
            LEFT JOIN spend s ON s.uid = p.uid
            """,
            self.engine,
        )
        logger.info("Built customer table: %d people", len(self._table))
        return self._table

    def summary(self) -> CustomerSummary:
        """
        Headline numbers.

        TWO REPEAT RATES, ON PURPOSE:
            repeat_rate_pct counts anyone with 2+ orders (3.12%) - it
            matches Module 8's repeat_customer_rate_pct exactly.
            returned_after_24h_rate_pct only counts people who placed an
            order at least 24 hours after their first. Profiling showed
            927 of the 2,997 repeat customers placed their second order
            within 24 hours of the first (see quick_followup_analysis()),
            so the headline rate overstates customers who actually come
            back later. Both are shown rather than hiding either.

        SPEND STATS COVER PAYING CUSTOMERS ONLY:
            676 people have zero spend (all their orders were cancelled
            or unavailable, so no items). Including them would drag the
            average toward zero for people who never bought anything.
            They are reported separately as zero_spend_customers.
        """
        t = self.customer_table()
        n = len(t)
        paying = t[t["spend"] > 0]
        repeat = t["orders"] > 1
        returned = t["return_order"].notna()

        spend_sorted = paying["spend"].sort_values(ascending=False)
        top_k = math.ceil(len(spend_sorted) * 0.01)
        total_spend = float(spend_sorted.sum())
        top_share = 100 * float(spend_sorted.head(top_k).sum()) / total_spend if total_spend else 0.0

        days_to_return = (
            (t.loc[returned, "return_order"] - t.loc[returned, "first_order"]).dt.total_seconds() / 86400
        )

        return CustomerSummary(
            unique_customers=int(n),
            paying_customers=int(len(paying)),
            zero_spend_customers=int(n - len(paying)),
            one_time_customers=int((~repeat).sum()),
            repeat_customers=int(repeat.sum()),
            repeat_rate_pct=round(100 * float(repeat.sum()) / n, 2),
            returned_after_24h_customers=int(returned.sum()),
            returned_after_24h_rate_pct=round(100 * float(returned.sum()) / n, 2),
            avg_orders_per_customer=round(float(t["orders"].mean()), 3),
            avg_spend=round(float(paying["spend"].mean()), 2),
            median_spend=round(float(paying["spend"].median()), 2),
            p99_spend=round(float(paying["spend"].quantile(0.99)), 2),
            max_spend=round(float(paying["spend"].max()), 2),
            top_1pct_revenue_share_pct=round(top_share, 1),
            median_days_to_return=round(float(days_to_return.median()), 1) if len(days_to_return) else None,
            mean_days_to_return=round(float(days_to_return.mean()), 1) if len(days_to_return) else None,
        )

    def orders_per_customer(self) -> pd.DataFrame:
        """How many people placed 1, 2, 3, or 4+ orders. Sums to unique_customers."""
        orders = self.customer_table()["orders"]
        buckets = orders.clip(upper=4).map(lambda n: "4+" if n >= 4 else str(int(n)))
        counts = buckets.value_counts().reindex(["1", "2", "3", "4+"], fill_value=0)
        out = counts.rename_axis("orders_placed").reset_index(name="customers")
        out["pct"] = (100 * out["customers"] / out["customers"].sum()).round(2)
        return out

    def by_state(self) -> pd.DataFrame:
        """
        Customers and revenue by state (state of each person's most
        recent order, so the customers column sums to the true total).
        avg_spend is per PAYING customer in that state.
        """
        t = self.customer_table()
        g = t.groupby("state").agg(
            customers=("customer_unique_id", "count"),
            paying_customers=("spend", lambda s: int((s > 0).sum())),
            revenue=("spend", "sum"),
        ).reset_index()
        g["pct_of_customers"] = (100 * g["customers"] / g["customers"].sum()).round(2)
        g["avg_spend"] = (g["revenue"] / g["paying_customers"].where(g["paying_customers"] > 0)).round(2)
        g["revenue"] = g["revenue"].round(2)
        return g.sort_values("customers", ascending=False).reset_index(drop=True)

    def top_cities(self, n: int = 10) -> pd.DataFrame:
        """
        Top cities by customers. Grouped by (city, state), NOT city
        alone: verified that the same city name exists in several
        states (e.g. 'boa esperanca' appears in 4), so grouping by name
        alone would merge unrelated towns.
        """
        t = self.customer_table()
        g = t.groupby(["city", "state"]).size().reset_index(name="customers")
        g = g.sort_values(["customers", "city"], ascending=[False, True]).head(n).reset_index(drop=True)
        g["label"] = g["city"].str.title() + " (" + g["state"] + ")"
        return g

    def new_vs_returning_monthly(self) -> pd.DataFrame:
        """
        For each month: how many active people were NEW (their first
        ever order was that month) vs RETURNING (they first ordered in
        an EARLIER month). A person is 'new' in exactly one month, so
        new_customers summed over all months equals unique_customers.

        A repeat order in the SAME month as the first still counts the
        person as new that month - 'returning' means they came back in
        a later month.
        """
        return pd.read_sql(
            """
            WITH activity AS (
                SELECT DISTINCT c.customer_unique_id AS uid,
                       DATE_TRUNC('month', o.order_purchase_timestamp) AS month
                FROM customers c JOIN orders o ON o.customer_id = c.customer_id
            ),
            first_month AS (
                SELECT uid, MIN(month) AS first_month FROM activity GROUP BY uid
            )
            SELECT a.month,
                   COUNT(*) FILTER (WHERE a.month = f.first_month) AS new_customers,
                   COUNT(*) FILTER (WHERE a.month > f.first_month) AS returning_customers
            FROM activity a JOIN first_month f ON f.uid = a.uid
            GROUP BY a.month
            ORDER BY a.month
            """,
            self.engine,
        )

    def top_customers(self, n: int = 10) -> pd.DataFrame:
        """Highest-spending people (anonymised ids as in the source data)."""
        t = self.customer_table()
        cols = ["customer_unique_id", "state", "orders", "spend"]
        top = t.sort_values(["spend", "customer_unique_id"], ascending=[False, True]).head(n)[cols]
        top = top.reset_index(drop=True)
        top["spend"] = top["spend"].round(2)
        return top

    def quick_followup_analysis(self) -> Dict[str, int]:
        """
        Looks at 'single-session repeaters': people with 2+ orders who
        placed ALL of them within 24 hours of their first. For each, it
        compares the sellers on their first two orders.

        WHY: if those quick follow-ups were one shopping trip split into
        several orders, the two orders would usually involve DIFFERENT
        sellers. Measured on the real data: a clear majority involve
        different sellers, but a meaningful minority share a seller, so
        'split basket' is a likely explanation for many - not all - of
        them. This is reported as evidence, not asserted as fact.
        """
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                WITH ord AS (
                    SELECT c.customer_unique_id AS uid, o.order_id, o.order_purchase_timestamp AS ts,
                           ROW_NUMBER() OVER (
                               PARTITION BY c.customer_unique_id
                               ORDER BY o.order_purchase_timestamp, o.order_id
                           ) AS rn
                    FROM customers c JOIN orders o ON o.customer_id = c.customer_id
                ),
                single_session AS (
                    SELECT uid FROM ord GROUP BY uid
                    HAVING COUNT(*) > 1 AND MAX(ts) < MIN(ts) + INTERVAL '1 day'
                ),
                pairs AS (
                    SELECT a.uid, a.order_id AS o1, b.order_id AS o2
                    FROM ord a
                    JOIN ord b ON a.uid = b.uid AND a.rn = 1 AND b.rn = 2
                    JOIN single_session ss ON ss.uid = a.uid
                ),
                order_sellers AS (
                    SELECT order_id, ARRAY_AGG(DISTINCT seller_id) AS seller_ids
                    FROM order_items
                    GROUP BY order_id
                ),
                seller_pairs AS (
                    SELECT p.uid, s1.seller_ids AS s1, s2.seller_ids AS s2
                    FROM pairs p
                    LEFT JOIN order_sellers s1 ON s1.order_id = p.o1
                    LEFT JOIN order_sellers s2 ON s2.order_id = p.o2
                )
                SELECT COUNT(*) AS single_session_repeaters,
                       COUNT(*) FILTER (WHERE COALESCE(cardinality(s1), 0) = 0
                                          OR COALESCE(cardinality(s2), 0) = 0) AS no_items,
                       COUNT(*) FILTER (WHERE cardinality(s1) > 0 AND cardinality(s2) > 0
                                          AND NOT (s1 && s2)) AS different_sellers,
                       COUNT(*) FILTER (WHERE cardinality(s1) > 0 AND cardinality(s2) > 0
                                          AND (s1 && s2)) AS shares_a_seller
                FROM seller_pairs
            """)).fetchone()
        return {
            "single_session_repeaters": int(row.single_session_repeaters),
            "different_sellers": int(row.different_sellers),
            "shares_a_seller": int(row.shares_a_seller),
            "no_items": int(row.no_items),
        }


def main() -> None:
    """CLI entry point: `python services/customer_analytics.py`."""
    if not db.test_connection():
        print("Cannot analyse customers - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    ca = CustomerAnalytics()
    summary = ca.summary()
    print("\n=== Customer Summary ===")
    for field, value in summary.__dict__.items():
        print(f"  {field}: {value}")
    print("\n=== Orders per customer ===")
    print(ca.orders_per_customer().to_string(index=False))
    print("\n=== Top 5 states by customers ===")
    print(ca.by_state().head(5).to_string(index=False))
    print("\n=== Quick follow-up analysis ===")
    print(ca.quick_followup_analysis())


if __name__ == "__main__":
    main()
