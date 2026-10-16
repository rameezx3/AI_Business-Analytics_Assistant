"""Evidence-backed recommendation rules for customer retention, reviews, and delivery."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from database.connection import db


class RecommendationEngine:
    """Create transparent business actions from existing, validated analytics."""

    def __init__(self) -> None:
        self.engine = db.engine

    def regional_delivery(self) -> pd.DataFrame:
        """One row per buyer state with order-level (not item-weighted) delivery time."""
        return pd.read_sql(text("""
            WITH orders_by_state AS (
                SELECT c.customer_state AS state,
                       COUNT(*) AS orders,
                       AVG(EXTRACT(EPOCH FROM
                           (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400.0)
                           FILTER (WHERE o.order_status = 'delivered'
                                   AND o.order_delivered_customer_date IS NOT NULL) AS avg_delivery_days,
                       COUNT(*) FILTER (WHERE o.order_status = 'delivered'
                                       AND o.order_delivered_customer_date IS NOT NULL) AS delivered_orders
                FROM customers c JOIN orders o ON o.customer_id = c.customer_id
                WHERE c.customer_state IS NOT NULL
                GROUP BY c.customer_state
            ), sales_by_state AS (
                SELECT c.customer_state AS state,
                       COUNT(DISTINCT oi.order_id) AS sales_orders,
                       SUM(oi.price) AS gross_sales
                FROM order_items oi
                JOIN orders o ON o.order_id = oi.order_id
                JOIN customers c ON c.customer_id = o.customer_id
                WHERE c.customer_state IS NOT NULL
                GROUP BY c.customer_state
            )
            SELECT o.state, o.orders, o.delivered_orders,
                   o.avg_delivery_days::double precision AS avg_delivery_days,
                   COALESCE(s.sales_orders, 0)::bigint AS sales_orders,
                   COALESCE(s.gross_sales, 0)::double precision AS gross_sales
            FROM orders_by_state o
            LEFT JOIN sales_by_state s ON s.state = o.state
            ORDER BY o.orders DESC
        """), self.engine)

    @staticmethod
    def generate(
        customer_segments: pd.DataFrame,
        total_customers: int,
        categories: pd.DataFrame,
        regional: pd.DataFrame,
    ) -> list[dict[str, object]]:
        """Apply documented signal thresholds and return auditable actions.

        The thresholds are screening rules, not causal evidence or estimates
        of the revenue a recommendation would produce.
        """
        recommendations: list[dict[str, object]] = []

        at_risk_rows = customer_segments.loc[customer_segments["segment"] == "At risk"]
        if not at_risk_rows.empty:
            at_risk = at_risk_rows.iloc[0]
            count = int(at_risk["customers"])
            revenue_share = float(at_risk["revenue_share_pct"])
            if count >= 100 and revenue_share >= 5:
                recommendations.append({
                    "priority": "High" if revenue_share >= 20 else "Medium",
                    "area": "Customer retention",
                    "title": "Run a measured win-back pilot for high-value at-risk customers",
                    "signal": "The historical at-risk segment is large enough to merit a targeted retention test.",
                    "evidence": [
                        f"{count:,} people ({100 * count / max(total_customers, 1):.1f}% of the customer base) are in the RFM At risk segment.",
                        f"That segment accounts for {revenue_share:.2f}% of observed item-price sales.",
                        f"Its mean recorded item spend is R$ {float(at_risk['avg_spend']):,.2f} per person.",
                    ],
                    "action": "Test a small, low-cost re-engagement campaign and compare repeat purchases and contribution margin with a holdout group before scaling. Avoid a blanket discount until the test shows incremental value.",
                    "rule": "At risk segment has at least 100 customers and contributes at least 5% of item sales.",
                    "limitation": "RFM recency is relative to the final date in this historical dataset; it does not indicate who is currently at risk.",
                })

        if not categories.empty:
            rated = categories.loc[categories["reviewed_orders"] > 0].copy()
            if not rated.empty:
                rating_baseline = float((rated["avg_review"] * rated["reviewed_orders"]).sum()
                                        / rated["reviewed_orders"].sum())
                sales_cutoff = float(categories["gross_sales"].quantile(0.75))
                flagged = categories.loc[
                    (categories["reviewed_orders"] >= 100)
                    & (categories["gross_sales"] >= sales_cutoff)
                    & (categories["avg_review"] <= rating_baseline - 0.25)
                ].sort_values("gross_sales", ascending=False)
                if not flagged.empty:
                    evidence = []
                    category_names = []
                    for row in flagged.head(5).itertuples(index=False):
                        category_names.append(str(row.category))
                        evidence.append(
                            f"{row.category}: R$ {float(row.gross_sales):,.0f} in item sales, "
                            f"{float(row.avg_review):.2f}/5 average score across {int(row.reviewed_orders):,} reviewed orders."
                        )
                    recommendations.append({
                        "priority": "High",
                        "area": "Product experience",
                        "title": "Investigate well-selling categories with weaker review scores",
                        "signal": "A high-sales category is materially below the dataset-wide order-review baseline.",
                        "evidence": [
                            f"Weighted review baseline: {rating_baseline:.2f}/5; high-sales threshold: R$ {sales_cutoff:,.0f}.",
                            *evidence,
                        ],
                        "action": "Review low-scoring order comments and inspect the leading products in "
                                  + ", ".join(category_names)
                                  + ". Identify whether complaints point to product expectations, condition, or fulfillment before changing listings or suppliers.",
                        "rule": "Category has at least 100 reviewed orders, item sales at or above the category 75th percentile, and average score at least 0.25 points below the weighted baseline.",
                        "limitation": "Order scores are associated with every category in a multi-category order; they do not prove which item caused a review.",
                    })

        if not regional.empty:
            delivered = regional.loc[
                regional["avg_delivery_days"].notna() & (regional["delivered_orders"] > 0)
            ]
            if not delivered.empty:
                baseline = float((delivered["avg_delivery_days"] * delivered["delivered_orders"]).sum()
                                 / delivered["delivered_orders"].sum())
                total_sales = max(float(regional["gross_sales"].sum()), 1.0)
                regional = regional.copy()
                regional["sales_share_pct"] = 100 * regional["gross_sales"] / total_sales
                flagged = regional.loc[
                    (regional["orders"] >= 1000)
                    & (regional["sales_share_pct"] >= 2)
                    & (regional["avg_delivery_days"] > baseline * 1.15)
                ].sort_values("gross_sales", ascending=False)
                if not flagged.empty:
                    evidence = [
                        f"Order-weighted delivery baseline: {baseline:.2f} days.",
                        *[
                            f"{row.state}: {float(row.avg_delivery_days):.2f} days across "
                            f"{int(row.delivered_orders):,} delivered orders; "
                            f"{float(row.sales_share_pct):.1f}% of item sales."
                            for row in flagged.head(5).itertuples(index=False)
                        ],
                    ]
                    states = ", ".join(str(state) for state in flagged.head(5)["state"])
                    recommendations.append({
                        "priority": "High" if float(flagged.iloc[0]["avg_delivery_days"]) > baseline * 1.3 else "Medium",
                        "area": "Fulfillment",
                        "title": "Review delivery performance in significant, slower markets",
                        "signal": "Some high-volume states have longer delivery times than the order-weighted dataset baseline.",
                        "evidence": evidence,
                        "action": f"Start a delivery-process review for {states}. Compare seller origin, route distance, and order hand-off timelines before changing carrier or service policies.",
                        "rule": "State has at least 1,000 orders, at least 2% of item sales, and order-level mean delivery time more than 15% above the overall delivered-order baseline.",
                        "limitation": "This is a historical association; distance, product mix, and customer expectations may explain part of the gap.",
                    })

        return recommendations
