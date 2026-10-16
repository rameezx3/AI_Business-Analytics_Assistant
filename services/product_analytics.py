"""Product and category performance analytics for the Olist dataset."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import text

from database.connection import db
from utils.logger import get_logger

logger = get_logger(__name__)


class ProductAnalytics:
    """Read-only product summaries; monetary sales use item price (freight excluded)."""

    def __init__(self) -> None:
        self.engine = db.engine

    def summary(self) -> dict:
        row = pd.read_sql(text("""
            SELECT COUNT(DISTINCT p.product_id) AS products,
                   COUNT(DISTINCT oi.product_id) AS products_sold,
                   COALESCE(SUM(oi.price), 0) AS gross_sales,
                   COUNT(oi.order_id) AS items_sold,
                   COUNT(DISTINCT oi.order_id) AS orders_with_products,
                   COUNT(DISTINCT p.product_category_name) AS categories
            FROM products p LEFT JOIN order_items oi ON oi.product_id = p.product_id
        """), self.engine).iloc[0]
        reviews = pd.read_sql(text("""
            SELECT COUNT(*) AS reviews, AVG(r.review_score) AS avg_score
            FROM order_reviews r
        """), self.engine).iloc[0]
        return {
            "products": int(row.products), "products_sold": int(row.products_sold),
            "gross_sales": float(row.gross_sales), "items_sold": int(row.items_sold),
            "orders_with_products": int(row.orders_with_products), "categories": int(row.categories),
            "reviews": int(reviews.reviews), "avg_review": float(reviews.avg_score or 0),
        }

    def categories(self) -> pd.DataFrame:
        """One row per category with item sales, distinct products/orders, and review mix."""
        return pd.read_sql(text("""
            WITH sales AS (
                SELECT p.product_category_name AS category_key,
                       COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized') AS category,
                       COUNT(*) AS items_sold, COUNT(DISTINCT oi.product_id) AS products,
                       COUNT(DISTINCT oi.order_id) AS orders, SUM(oi.price) AS gross_sales,
                       AVG(oi.price) AS avg_item_price
                FROM products p
                JOIN order_items oi ON oi.product_id = p.product_id
                LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
                GROUP BY p.product_category_name, ct.product_category_name_english
            ),
            rated_order_categories AS (
                SELECT DISTINCT oi.order_id, p.product_category_name AS category_key, r.order_score
                FROM order_items oi JOIN products p ON p.product_id = oi.product_id
                JOIN (SELECT order_id, AVG(review_score) AS order_score
                      FROM order_reviews GROUP BY order_id) r ON r.order_id = oi.order_id
            ),
            rating AS (
                SELECT category_key, AVG(order_score) AS avg_review,
                       COUNT(*) AS reviewed_orders,
                       COUNT(*) FILTER (WHERE order_score <= 2) AS low_review_orders,
                       COUNT(*) FILTER (WHERE order_score >= 4) AS positive_review_orders
                FROM rated_order_categories GROUP BY category_key
            )
            SELECT s.category, s.items_sold, s.products, s.orders, s.gross_sales,
                   s.avg_item_price, COALESCE(r.avg_review, 0) AS avg_review,
                   COALESCE(r.reviewed_orders, 0) AS reviewed_orders,
                   COALESCE(r.low_review_orders, 0) AS low_review_orders,
                   COALESCE(r.positive_review_orders, 0) AS positive_review_orders
            FROM sales s LEFT JOIN rating r ON r.category_key IS NOT DISTINCT FROM s.category_key
            ORDER BY s.gross_sales DESC
        """), self.engine)

    def top_products(self, n: int = 10, *, worst: bool = False, min_items: int = 5) -> pd.DataFrame:
        """Products ranked by item sales; worst sellers require a minimum volume for context."""
        direction = "ASC" if worst else "DESC"
        query = text(f"""
            WITH item_sales AS (
                SELECT product_id, COUNT(*) AS items_sold,
                       COUNT(DISTINCT order_id) AS orders,
                       SUM(price) AS gross_sales, AVG(price) AS avg_price
                FROM order_items GROUP BY product_id
            ), rated_orders AS (
                SELECT DISTINCT oi.product_id, oi.order_id, r.order_score
                FROM order_items oi
                JOIN (SELECT order_id, AVG(review_score) AS order_score
                      FROM order_reviews GROUP BY order_id) r ON r.order_id = oi.order_id
            ), ratings AS (
                SELECT product_id, AVG(order_score) AS avg_review,
                       COUNT(*) AS reviews
                FROM rated_orders GROUP BY product_id
            )
            SELECT p.product_id,
                   COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized') AS category,
                   s.items_sold, s.orders, s.gross_sales, s.avg_price,
                   p.product_photos_qty AS photos, p.product_description_lenght AS description_length,
                   COALESCE(r.avg_review, 0) AS avg_review, COALESCE(r.reviews, 0) AS reviews
            FROM products p JOIN item_sales s ON s.product_id = p.product_id
            LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
            LEFT JOIN ratings r ON r.product_id = p.product_id
            WHERE s.items_sold >= :min_items
            ORDER BY s.gross_sales {direction}, p.product_id
            LIMIT :limit
        """)
        return pd.read_sql(query, self.engine, params={"min_items": min_items, "limit": n})

    def content_signals(self) -> pd.DataFrame:
        """Compare product sales across photo-count and description-length bands."""
        return pd.read_sql(text("""
            WITH per_product AS (
                SELECT p.product_id, p.product_photos_qty AS photos,
                       p.product_description_lenght AS description_length,
                       COUNT(oi.order_id) AS items_sold, SUM(oi.price) AS gross_sales
                FROM products p LEFT JOIN order_items oi ON oi.product_id = p.product_id
                GROUP BY p.product_id, p.product_photos_qty, p.product_description_lenght
            ), bucketed AS (
                SELECT *, CASE WHEN photos IS NULL THEN 'Unknown'
                               WHEN photos <= 1 THEN '0–1 photos'
                               WHEN photos <= 3 THEN '2–3 photos'
                               WHEN photos <= 6 THEN '4–6 photos' ELSE '7+ photos' END AS photo_band,
                          CASE WHEN description_length IS NULL THEN 'Unknown'
                               WHEN description_length < 300 THEN 'Short (<300)'
                               WHEN description_length < 1200 THEN 'Medium (300–1199)'
                               ELSE 'Long (1200+)' END AS description_band
                FROM per_product
            )
            SELECT photo_band, description_band, COUNT(*) AS products,
                   SUM(items_sold) AS items_sold,
                   ROUND(AVG(items_sold)::numeric, 2) AS avg_items_per_product,
                   ROUND(AVG(gross_sales)::numeric, 2) AS avg_sales_per_product
            FROM bucketed GROUP BY photo_band, description_band
            ORDER BY photo_band, description_band
        """), self.engine)

    def review_distribution(self) -> pd.DataFrame:
        return pd.read_sql(text("""
            SELECT review_score, COUNT(*) AS reviews
            FROM order_reviews GROUP BY review_score ORDER BY review_score
        """), self.engine)

