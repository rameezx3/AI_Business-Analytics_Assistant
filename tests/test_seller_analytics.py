import pandas as pd
from sqlalchemy import text

from database.connection import db
from services.seller_analytics import SellerAnalytics


def test_seller_performance_reconciles_with_raw_sales_and_seller_count():
    data = SellerAnalytics().performance()
    raw = pd.read_sql(text("SELECT (SELECT COUNT(*) FROM sellers) AS sellers, (SELECT SUM(price) FROM order_items) AS sales"), db.engine).iloc[0]
    assert len(data) == int(raw.sellers)
    assert data.seller_id.is_unique
    assert round(float(data.gross_sales.sum()), 2) == round(float(raw.sales), 2)
    assert int(data.items_sold.sum()) == pd.read_sql(text("SELECT COUNT(*) AS n FROM order_items"), db.engine).iloc[0].n
    assert (data.gross_sales >= 0).all()


def test_seller_ratings_are_based_on_distinct_seller_order_pairs():
    data = SellerAnalytics().performance()
    expected = pd.read_sql(text("""
        SELECT seller_id, AVG(review_score) AS avg_review, COUNT(*) AS reviewed_orders
        FROM (
            SELECT DISTINCT oi.seller_id, r.order_id, r.review_score
            FROM order_items oi
            JOIN (SELECT order_id, AVG(review_score) AS review_score FROM order_reviews GROUP BY order_id) r
              ON r.order_id = oi.order_id
        ) pairs GROUP BY seller_id
    """), db.engine)
    merged = data.merge(expected, on="seller_id", suffixes=("_service", "_raw"))
    assert (merged.reviewed_orders_service == merged.reviewed_orders_raw).all()
    assert (merged.avg_review_service - merged.avg_review_raw).abs().max() < 1e-9


def test_selected_seller_monthly_series_matches_seller_sales():
    analytics = SellerAnalytics()
    seller = analytics.performance().iloc[0]
    monthly = analytics.monthly_sales(seller.seller_id)
    assert not monthly.empty
    assert round(float(monthly.gross_sales.sum()), 2) == round(float(seller.gross_sales), 2)
    assert monthly.month.is_monotonic_increasing
