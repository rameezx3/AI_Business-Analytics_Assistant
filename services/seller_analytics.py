"""Seller performance analytics with order-level ratings protected from join fan-out."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import text

from database.connection import db


class SellerAnalytics:
    """Read-only seller summaries; sales are item prices and exclude freight."""

    def __init__(self) -> None:
        self.engine = db.engine

    def performance(self) -> pd.DataFrame:
        """Return one row per seller with sales, order-level ratings, and fulfillment."""
        return pd.read_sql(text("""
            WITH sales AS (
                SELECT oi.seller_id, COUNT(*) AS items_sold,
                       COUNT(DISTINCT oi.order_id) AS orders,
                       SUM(oi.price) AS gross_sales,
                       AVG(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400.0)
                           FILTER (WHERE o.order_delivered_customer_date IS NOT NULL) AS avg_delivery_days
                FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
                GROUP BY oi.seller_id
            ), seller_order_reviews AS (
                SELECT DISTINCT oi.seller_id, r.order_id, r.review_score
                FROM order_items oi
                JOIN (SELECT order_id, AVG(review_score) AS review_score
                      FROM order_reviews GROUP BY order_id) r ON r.order_id = oi.order_id
            ), ratings AS (
                SELECT seller_id, AVG(review_score) AS avg_review,
                       COUNT(*) AS reviewed_orders,
                       COUNT(*) FILTER (WHERE review_score <= 2) AS low_review_orders
                FROM seller_order_reviews GROUP BY seller_id
            )
            SELECT s.seller_id, s.seller_state AS state, s.seller_city AS city,
                   COALESCE(x.items_sold, 0)::bigint AS items_sold,
                   COALESCE(x.orders, 0)::bigint AS orders,
                   COALESCE(x.gross_sales, 0)::double precision AS gross_sales,
                   x.avg_delivery_days::double precision AS avg_delivery_days,
                   r.avg_review::double precision AS avg_review,
                   COALESCE(r.reviewed_orders, 0)::bigint AS reviewed_orders,
                   COALESCE(r.low_review_orders, 0)::bigint AS low_review_orders
            FROM sellers s
            LEFT JOIN sales x ON x.seller_id = s.seller_id
            LEFT JOIN ratings r ON r.seller_id = s.seller_id
            ORDER BY gross_sales DESC, orders DESC, s.seller_id
        """), self.engine)

    def monthly_sales(self, seller_id: str) -> pd.DataFrame:
        """Return monthly item sales for one selected seller."""
        return pd.read_sql(text("""
            SELECT DATE_TRUNC('month', o.order_purchase_timestamp) AS month,
                   COUNT(DISTINCT oi.order_id) AS orders,
                   SUM(oi.price)::double precision AS gross_sales
            FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
            WHERE oi.seller_id = :seller_id
            GROUP BY 1 ORDER BY 1
        """), self.engine, params={"seller_id": seller_id})
