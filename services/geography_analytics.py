"""State-level performance and seller/customer distance analytics."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from database.connection import db


class GeographyAnalytics:
    def __init__(self) -> None:
        self.engine = db.engine

    def state_performance(self) -> pd.DataFrame:
        """Aggregate order counts, item sales, and delivery time by buyer state."""
        return pd.read_sql("""
            WITH zip_points AS (
                SELECT geolocation_zip_code_prefix AS zip,
                       AVG(geolocation_lat) AS lat, AVG(geolocation_lng) AS lng
                FROM geolocation GROUP BY geolocation_zip_code_prefix
            )
            SELECT c.customer_state AS state,
                   COUNT(DISTINCT o.order_id) AS orders,
                   COALESCE(SUM(oi.price), 0)::double precision AS gross_sales,
                   AVG(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400.0)
                       FILTER (WHERE o.order_delivered_customer_date IS NOT NULL)::double precision AS avg_delivery_days,
                   AVG(g.lat)::double precision AS lat, AVG(g.lng)::double precision AS lng
            FROM customers c
            JOIN orders o ON o.customer_id = c.customer_id
            LEFT JOIN order_items oi ON oi.order_id = o.order_id
            LEFT JOIN zip_points g ON g.zip = c.customer_zip_code_prefix
            WHERE c.customer_state IS NOT NULL
            GROUP BY c.customer_state
            ORDER BY gross_sales DESC
        """, self.engine)

    def distance_summary(self) -> dict:
        """Compute great-circle distance between buyer/seller ZIP centroids per order item."""
        row = pd.read_sql("""
            WITH zip_points AS (
                SELECT geolocation_zip_code_prefix AS zip,
                       AVG(geolocation_lat) AS lat, AVG(geolocation_lng) AS lng
                FROM geolocation
                WHERE geolocation_lat BETWEEN -34 AND 6
                  AND geolocation_lng BETWEEN -74 AND -34
                GROUP BY geolocation_zip_code_prefix
            ), pairs AS (
                SELECT c.customer_state, s.seller_state,
                    6371.0 * ACOS(LEAST(1.0, GREATEST(-1.0,
                      COS(RADIANS(cp.lat)) * COS(RADIANS(sp.lat)) *
                      COS(RADIANS(sp.lng - cp.lng)) + SIN(RADIANS(cp.lat)) * SIN(RADIANS(sp.lat))
                    ))) AS distance_km
                FROM order_items oi
                JOIN orders o ON o.order_id = oi.order_id
                JOIN customers c ON c.customer_id = o.customer_id
                JOIN sellers s ON s.seller_id = oi.seller_id
                JOIN zip_points cp ON cp.zip = c.customer_zip_code_prefix
                JOIN zip_points sp ON sp.zip = s.seller_zip_code_prefix
            )
            SELECT COUNT(*)::bigint AS items_with_locations,
                   AVG(distance_km)::double precision AS avg_distance_km,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY distance_km)::double precision AS median_distance_km,
                   COUNT(*) FILTER (WHERE customer_state <> seller_state)::bigint AS cross_state_items
            FROM pairs WHERE distance_km IS NOT NULL
        """, self.engine).iloc[0]
        count = int(row["items_with_locations"] or 0)
        cross = int(row["cross_state_items"] or 0)
        return {
            "items_with_locations": count,
            "avg_distance_km": float(row["avg_distance_km"] or 0),
            "median_distance_km": float(row["median_distance_km"] or 0),
            "cross_state_pct": round(cross / count * 100, 2) if count else 0.0,
        }
