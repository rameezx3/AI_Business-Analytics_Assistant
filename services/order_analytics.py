"""Order-level analytics and detail queries for the Orders dashboard."""

from datetime import date

import pandas as pd
from sqlalchemy import text

from database.connection import db


class OrderAnalytics:
    """Read-only order queries with shared, parameterized filters."""

    def filter_options(self) -> dict:
        with db.engine.connect() as connection:
            dates = connection.execute(text("""
                SELECT MIN(order_purchase_timestamp)::date,
                       MAX(order_purchase_timestamp)::date
                FROM orders
                WHERE order_purchase_timestamp IS NOT NULL
            """)).one()
            statuses = [row[0] for row in connection.execute(text(
                "SELECT DISTINCT order_status FROM orders ORDER BY order_status"
            ))]
            states = [row[0] for row in connection.execute(text("""
                SELECT DISTINCT c.customer_state
                FROM orders o
                JOIN customers c ON c.customer_id = o.customer_id
                WHERE c.customer_state IS NOT NULL
                ORDER BY c.customer_state
            """))]
        return {"start": dates[0], "end": dates[1], "statuses": statuses, "states": states}

    @staticmethod
    def _where(
        start: date, end: date, statuses: tuple[str, ...], states: tuple[str, ...], search: str,
    ) -> tuple[str, dict]:
        clauses = [
            "o.order_purchase_timestamp >= :start_date",
            "o.order_purchase_timestamp < :end_exclusive",
        ]
        params: dict = {"start_date": start, "end_exclusive": end + pd.Timedelta(days=1)}
        if statuses:
            names = []
            for index, status in enumerate(statuses):
                key = f"status_{index}"
                names.append(f":{key}")
                params[key] = status
            clauses.append(f"o.order_status IN ({', '.join(names)})")
        if states:
            names = []
            for index, state in enumerate(states):
                key = f"state_{index}"
                names.append(f":{key}")
                params[key] = state
            clauses.append(f"c.customer_state IN ({', '.join(names)})")
        if search.strip():
            clauses.append("(o.order_id ILIKE :search OR c.customer_unique_id ILIKE :search)")
            params["search"] = f"%{search.strip()}%"
        return " AND ".join(clauses), params

    def _filtered_cte(self, where: str) -> str:
        return f"""
            WITH filtered_orders AS (
                SELECT o.order_id, o.customer_id, o.order_status,
                       o.order_purchase_timestamp, o.order_approved_at,
                       o.order_delivered_carrier_date, o.order_delivered_customer_date,
                       o.order_estimated_delivery_date, c.customer_unique_id,
                       c.customer_state
                FROM orders o
                LEFT JOIN customers c ON c.customer_id = o.customer_id
                WHERE {where}
            )
        """

    def overview(
        self, start: date, end: date, statuses: tuple[str, ...], states: tuple[str, ...], search: str,
    ) -> dict:
        where, params = self._where(start, end, statuses, states, search)
        cte = self._filtered_cte(where)
        with db.engine.connect() as connection:
            summary = connection.execute(text(cte + """
                SELECT COUNT(*) AS total_orders,
                       COUNT(*) FILTER (WHERE f.order_status = 'delivered') AS delivered_orders,
                       COALESCE(SUM(i.item_value), 0) AS item_value,
                       AVG(EXTRACT(EPOCH FROM (f.order_delivered_customer_date - f.order_purchase_timestamp)) / 86400.0)
                           FILTER (WHERE f.order_delivered_customer_date IS NOT NULL) AS avg_delivery_days,
                       COUNT(*) FILTER (WHERE f.order_approved_at IS NOT NULL) AS approved_orders,
                       COUNT(*) FILTER (WHERE f.order_delivered_carrier_date IS NOT NULL) AS carrier_handoffs,
                       COUNT(*) FILTER (WHERE f.order_delivered_customer_date IS NOT NULL) AS customer_deliveries
                FROM filtered_orders f
                LEFT JOIN (
                    SELECT order_id, SUM(price) AS item_value
                    FROM order_items GROUP BY order_id
                ) i ON i.order_id = f.order_id
            """), params).mappings().one()
            statuses_df = pd.read_sql_query(text(cte + """
                SELECT f.order_status AS status, COUNT(*) AS orders
                FROM filtered_orders f
                GROUP BY f.order_status ORDER BY orders DESC, status
            """), connection, params=params)
            punctuality_df = pd.read_sql_query(text(cte + """
                SELECT CASE
                           WHEN f.order_estimated_delivery_date IS NULL THEN 'No estimate'
                           WHEN f.order_delivered_customer_date <= f.order_estimated_delivery_date THEN 'On time / early'
                           ELSE 'Late'
                       END AS outcome,
                       COUNT(*) AS orders
                FROM filtered_orders f
                WHERE f.order_status = 'delivered'
                  AND f.order_delivered_customer_date IS NOT NULL
                GROUP BY outcome
                ORDER BY outcome
            """), connection, params=params)
        return {
            "summary": dict(summary),
            "statuses": statuses_df,
            "punctuality": punctuality_df,
        }

    def count(
        self, start: date, end: date, statuses: tuple[str, ...], states: tuple[str, ...], search: str,
    ) -> int:
        where, params = self._where(start, end, statuses, states, search)
        with db.engine.connect() as connection:
            return int(connection.execute(text(self._filtered_cte(where) +
                "SELECT COUNT(*) FROM filtered_orders"), params).scalar_one())

    def page(
        self, start: date, end: date, statuses: tuple[str, ...], states: tuple[str, ...],
        search: str, limit: int, offset: int,
    ) -> pd.DataFrame:
        where, params = self._where(start, end, statuses, states, search)
        params.update({"limit": limit, "offset": offset})
        query = text(self._filtered_cte(where) + """
            SELECT f.order_id, f.order_purchase_timestamp, f.order_status,
                   f.customer_unique_id, f.customer_state,
                   COALESCE(i.item_value, 0) AS item_value,
                   COALESCE(i.freight_value, 0) AS freight_value,
                   COALESCE(p.payment_value, 0) AS payment_value,
                   r.review_score,
                   ROUND((EXTRACT(EPOCH FROM (f.order_delivered_customer_date - f.order_purchase_timestamp)) / 86400.0)::numeric, 1)
                       AS delivery_days,
                   ROUND((EXTRACT(EPOCH FROM (f.order_delivered_customer_date - f.order_estimated_delivery_date)) / 86400.0)::numeric, 1)
                       AS days_late
            FROM filtered_orders f
            LEFT JOIN (
                SELECT order_id, SUM(price) AS item_value, SUM(freight_value) AS freight_value
                FROM order_items GROUP BY order_id
            ) i ON i.order_id = f.order_id
            LEFT JOIN (
                SELECT order_id, SUM(payment_value) AS payment_value
                FROM order_payments GROUP BY order_id
            ) p ON p.order_id = f.order_id
            LEFT JOIN (
                SELECT order_id, ROUND(AVG(review_score)::numeric, 2) AS review_score
                FROM order_reviews GROUP BY order_id
            ) r ON r.order_id = f.order_id
            ORDER BY f.order_purchase_timestamp DESC NULLS LAST, f.order_id DESC
            LIMIT :limit OFFSET :offset
        """)
        return pd.read_sql_query(query, db.engine, params=params)

    def details(self, order_id: str) -> dict[str, pd.DataFrame]:
        with db.engine.connect() as connection:
            items = pd.read_sql_query(text("""
                SELECT oi.order_item_id AS item, COALESCE(ct.product_category_name_english,
                       p.product_category_name, 'Unknown') AS category,
                       oi.product_id, oi.seller_id, s.seller_state,
                       oi.price, oi.freight_value
                FROM order_items oi
                LEFT JOIN products p ON p.product_id = oi.product_id
                LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
                LEFT JOIN sellers s ON s.seller_id = oi.seller_id
                WHERE oi.order_id = :order_id
                ORDER BY oi.order_item_id
            """), connection, params={"order_id": order_id})
            payments = pd.read_sql_query(text("""
                SELECT payment_sequential AS sequence, payment_type, payment_installments,
                       payment_value
                FROM order_payments WHERE order_id = :order_id
                ORDER BY payment_sequential
            """), connection, params={"order_id": order_id})
            reviews = pd.read_sql_query(text("""
                SELECT review_score, review_comment_title, review_comment_message,
                       review_creation_date
                FROM order_reviews WHERE order_id = :order_id
                ORDER BY review_creation_date DESC NULLS LAST
            """), connection, params={"order_id": order_id})
        return {"items": items, "payments": payments, "reviews": reviews}
