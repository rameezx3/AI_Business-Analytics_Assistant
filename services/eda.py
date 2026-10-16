"""
services/eda.py

WHY THIS FILE EXISTS:
    Module 6: Exploratory Data Analysis. Distinct from the later
    Interactive Dashboard (Module 7) and the per-domain Analytics
    modules (10-14) - this is the broad, first-pass "what does this
    dataset actually look like" exploration: distributions, trends,
    categorical breakdowns, and correlations, produced as static charts
    (charts/generated/) plus a written findings report
    (reports/generated/eda_report.md).

    Every chart pulls real data straight from PostgreSQL via pandas -
    nothing here is a mocked or illustrative figure.

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/eda.py

USAGE:
    python services/eda.py
"""

import sys
from pathlib import Path
from typing import Dict

sys.path.append(str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")  # no display available - write straight to PNG files
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from config import config
from database.connection import db
from utils.logger import get_logger

logger = get_logger(__name__)

sns.set_theme(style="whitegrid")
FIGSIZE_WIDE = (10, 5)
FIGSIZE_SQUARE = (7, 6)


class EDAAnalyzer:
    """
    Runs a fixed set of exploratory analyses against the cleaned,
    validated data (Modules 4-5) and produces:
        - one PNG chart per analysis, saved to charts/generated/
        - one combined markdown report, saved to reports/generated/

    Each `analyze_*` method returns a small dict of the real numbers it
    computed, which run_all() collects into the final report - so the
    report text is always generated FROM the computed numbers, never
    written independently of them.
    """

    def __init__(self) -> None:
        self.engine = db.engine
        self.charts_dir: Path = config.app.charts_dir
        self.reports_dir: Path = config.app.reports_dir
        self.findings: Dict[str, dict] = {}

    def _save_fig(self, filename: str) -> Path:
        path = self.charts_dir / filename
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        logger.info("Saved chart: %s", path)
        return path

    def analyze_monthly_order_trend(self) -> dict:
        """Order volume by month across the full 2016-2018 dataset window."""
        df = pd.read_sql(
            """
            SELECT DATE_TRUNC('month', order_purchase_timestamp) AS month, COUNT(*) AS orders
            FROM orders
            GROUP BY 1 ORDER BY 1
            """,
            self.engine,
        )
        plt.figure(figsize=FIGSIZE_WIDE)
        plt.plot(df["month"], df["orders"], marker="o", linewidth=2)
        plt.title("Monthly Order Volume (2016-2018)")
        plt.xlabel("Month")
        plt.ylabel("Number of Orders")
        plt.xticks(rotation=45)
        self._save_fig("01_monthly_order_trend.png")

        peak = df.loc[df["orders"].idxmax()]
        return {
            "peak_month": str(peak["month"].date()),
            "peak_orders": int(peak["orders"]),
            "total_months": len(df),
        }

    def analyze_order_status_distribution(self) -> dict:
        """How orders break down by fulfillment status."""
        df = pd.read_sql(
            "SELECT order_status, COUNT(*) AS n FROM orders GROUP BY order_status ORDER BY n DESC",
            self.engine,
        )
        plt.figure(figsize=FIGSIZE_WIDE)
        sns.barplot(data=df, x="n", y="order_status", hue="order_status", legend=False, palette="viridis")
        plt.title("Orders by Status")
        plt.xlabel("Number of Orders")
        plt.ylabel("Status")
        self._save_fig("02_order_status_distribution.png")

        total = int(df["n"].sum())
        delivered_pct = round(100 * int(df.loc[df["order_status"] == "delivered", "n"].iloc[0]) / total, 1)
        return {"total_orders": total, "delivered_pct": delivered_pct}

    def analyze_revenue_by_category(self) -> dict:
        """Top 10 product categories by total item revenue (delivered orders only)."""
        df = pd.read_sql(
            """
            SELECT ct.product_category_name_english AS category, ROUND(SUM(oi.price)::numeric, 2) AS revenue
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            JOIN category_translation ct ON p.product_category_name = ct.product_category_name
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_status = 'delivered'
            GROUP BY category ORDER BY revenue DESC LIMIT 10
            """,
            self.engine,
        )
        plt.figure(figsize=FIGSIZE_WIDE)
        sns.barplot(data=df, x="revenue", y="category", hue="category", legend=False, palette="mako")
        plt.title("Top 10 Product Categories by Revenue (Delivered Orders)")
        plt.xlabel("Revenue (R$)")
        plt.ylabel("Category")
        self._save_fig("03_top_categories_by_revenue.png")

        return {
            "top_category": df.iloc[0]["category"],
            "top_category_revenue": float(df.iloc[0]["revenue"]),
        }

    def analyze_payment_types(self) -> dict:
        """How customers pay."""
        df = pd.read_sql(
            "SELECT payment_type, COUNT(*) AS n FROM order_payments GROUP BY payment_type ORDER BY n DESC",
            self.engine,
        )
        plt.figure(figsize=FIGSIZE_SQUARE)
        colors = sns.color_palette("pastel", len(df))
        plt.pie(df["n"], labels=df["payment_type"], autopct="%1.1f%%", colors=colors, startangle=90)
        plt.title("Payment Method Distribution")
        self._save_fig("04_payment_type_distribution.png")

        total = int(df["n"].sum())
        top_pct = round(100 * int(df.iloc[0]["n"]) / total, 1)
        return {"most_common_method": df.iloc[0]["payment_type"], "most_common_pct": top_pct}

    def analyze_review_scores(self) -> dict:
        """Customer satisfaction distribution."""
        df = pd.read_sql("SELECT review_score FROM order_reviews", self.engine)
        plt.figure(figsize=FIGSIZE_WIDE)
        sns.countplot(data=df, x="review_score", hue="review_score", legend=False, palette="RdYlGn")
        plt.title("Review Score Distribution")
        plt.xlabel("Score (1-5)")
        plt.ylabel("Number of Reviews")
        self._save_fig("05_review_score_distribution.png")

        return {
            "avg_score": round(float(df["review_score"].mean()), 2),
            "pct_5_star": round(float((df["review_score"] == 5).mean()) * 100, 1),
            "pct_1_star": round(float((df["review_score"] == 1).mean()) * 100, 1),
        }

    def analyze_price_distribution(self) -> dict:
        """
        Item price distribution. Uses a log-scale x-axis - verified the
        raw distribution is heavily right-skewed (most items are cheap,
        a long tail of expensive ones), so a linear-scale histogram
        would just show one tall bar near zero and hide the shape.
        """
        df = pd.read_sql("SELECT price FROM order_items WHERE price > 0", self.engine)
        plt.figure(figsize=FIGSIZE_WIDE)
        sns.histplot(df["price"], bins=60, log_scale=True, color="steelblue")
        plt.title("Order Item Price Distribution (log scale)")
        plt.xlabel("Price (R$, log scale)")
        plt.ylabel("Count")
        self._save_fig("06_price_distribution.png")

        return {
            "median_price": round(float(df["price"].median()), 2),
            "p95_price": round(float(df["price"].quantile(0.95)), 2),
            "max_price": round(float(df["price"].max()), 2),
        }

    def analyze_delivery_time(self) -> dict:
        """Days between purchase and actual delivery, for delivered orders."""
        df = pd.read_sql(
            """
            SELECT EXTRACT(EPOCH FROM (order_delivered_customer_date - order_purchase_timestamp)) / 86400 AS days
            FROM orders
            WHERE order_delivered_customer_date IS NOT NULL
            """,
            self.engine,
        )
        # A handful of extreme outliers (>100 days) exist and would
        # squash the histogram - clip the DISPLAY only, not the stats.
        plt.figure(figsize=FIGSIZE_WIDE)
        sns.histplot(df[df["days"] <= 60]["days"], bins=40, color="darkorange")
        plt.title("Delivery Time Distribution (purchase to delivery, capped at 60 days for display)")
        plt.xlabel("Days")
        plt.ylabel("Number of Orders")
        self._save_fig("07_delivery_time_distribution.png")

        return {
            "avg_days": round(float(df["days"].mean()), 1),
            "median_days": round(float(df["days"].median()), 1),
            "p95_days": round(float(df["days"].quantile(0.95)), 1),
        }

    def analyze_orders_by_state(self) -> dict:
        """Top 10 states by order volume."""
        df = pd.read_sql(
            """
            SELECT c.customer_state AS state, COUNT(*) AS orders
            FROM orders o JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY state ORDER BY orders DESC LIMIT 10
            """,
            self.engine,
        )
        plt.figure(figsize=FIGSIZE_WIDE)
        sns.barplot(data=df, x="orders", y="state", hue="state", legend=False, palette="crest")
        plt.title("Top 10 States by Order Volume")
        plt.xlabel("Number of Orders")
        plt.ylabel("State")
        self._save_fig("08_orders_by_state.png")

        return {"top_state": df.iloc[0]["state"], "top_state_orders": int(df.iloc[0]["orders"])}

    def analyze_correlations(self) -> dict:
        """Correlation between price, freight, review score, and delivery time."""
        df = pd.read_sql(
            """
            SELECT oi.price, oi.freight_value, r.review_score,
                   EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400 AS delivery_days
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            LEFT JOIN order_reviews r ON r.order_id = o.order_id
            WHERE o.order_delivered_customer_date IS NOT NULL AND r.review_score IS NOT NULL
            """,
            self.engine,
        )
        corr = df[["price", "freight_value", "review_score", "delivery_days"]].corr()

        plt.figure(figsize=FIGSIZE_SQUARE)
        sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, vmin=-1, vmax=1)
        plt.title("Correlation Matrix: Price, Freight, Review Score, Delivery Time")
        self._save_fig("09_correlation_heatmap.png")

        delivery_review_corr = round(float(corr.loc["delivery_days", "review_score"]), 3)
        return {"delivery_days_vs_review_score_corr": delivery_review_corr}

    def run_all(self) -> Dict[str, dict]:
        """Runs every analysis, in order, and writes the combined markdown report."""
        self.findings = {
            "monthly_order_trend": self.analyze_monthly_order_trend(),
            "order_status_distribution": self.analyze_order_status_distribution(),
            "revenue_by_category": self.analyze_revenue_by_category(),
            "payment_types": self.analyze_payment_types(),
            "review_scores": self.analyze_review_scores(),
            "price_distribution": self.analyze_price_distribution(),
            "delivery_time": self.analyze_delivery_time(),
            "orders_by_state": self.analyze_orders_by_state(),
            "correlations": self.analyze_correlations(),
        }
        self._write_report()
        return self.findings

    def _write_report(self) -> None:
        f = self.findings
        report = f"""# Exploratory Data Analysis Report

Generated automatically from the live PostgreSQL database (post-cleaning, Module 4;
post-validation, Module 5). Every number below comes directly from the queries in
`services/eda.py` - none of it is illustrative.

## 1. Order Volume Trend
Peak month: **{f['monthly_order_trend']['peak_month']}** with **{f['monthly_order_trend']['peak_orders']}** orders,
across {f['monthly_order_trend']['total_months']} months of data.
See `01_monthly_order_trend.png`.

## 2. Order Status
**{f['order_status_distribution']['delivered_pct']}%** of {f['order_status_distribution']['total_orders']} total
orders reached 'delivered' status. See `02_order_status_distribution.png`.

## 3. Revenue by Category
Top category by revenue: **{f['revenue_by_category']['top_category']}**
(R$ {f['revenue_by_category']['top_category_revenue']:,.2f}). See `03_top_categories_by_revenue.png`.

## 4. Payment Methods
Most common payment method: **{f['payment_types']['most_common_method']}**
({f['payment_types']['most_common_pct']}% of payments). See `04_payment_type_distribution.png`.

## 5. Review Scores
Average review score: **{f['review_scores']['avg_score']} / 5**.
{f['review_scores']['pct_5_star']}% of reviews are 5-star, {f['review_scores']['pct_1_star']}% are 1-star.
See `05_review_score_distribution.png`.

## 6. Price Distribution
Median item price: **R$ {f['price_distribution']['median_price']}**, 95th percentile:
R$ {f['price_distribution']['p95_price']}, maximum: R$ {f['price_distribution']['max_price']}.
Distribution is heavily right-skewed - see `06_price_distribution.png` (log scale).

## 7. Delivery Time
Average delivery time: **{f['delivery_time']['avg_days']} days** (median: {f['delivery_time']['median_days']},
95th percentile: {f['delivery_time']['p95_days']} days). See `07_delivery_time_distribution.png`.

## 8. Geographic Concentration
Top state by order volume: **{f['orders_by_state']['top_state']}** with
{f['orders_by_state']['top_state_orders']} orders. See `08_orders_by_state.png`.

## 9. Correlations
Correlation between delivery time and review score: **{f['correlations']['delivery_days_vs_review_score_corr']}**
(negative = slower delivery associates with lower review scores). See `09_correlation_heatmap.png`.
"""
        report_path = self.reports_dir / "eda_report.md"
        report_path.write_text(report, encoding="utf-8")
        logger.info("Wrote EDA report: %s", report_path)


def main() -> None:
    """CLI entry point: `python services/eda.py`."""
    if not db.test_connection():
        print("Cannot run EDA - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    analyzer = EDAAnalyzer()
    findings = analyzer.run_all()

    print("\n=== EDA Summary ===")
    for section, data in findings.items():
        print(f"  {section}: {data}")
    print(f"\nCharts saved to: {analyzer.charts_dir}")
    print(f"Report saved to: {analyzer.reports_dir / 'eda_report.md'}")


if __name__ == "__main__":
    main()
