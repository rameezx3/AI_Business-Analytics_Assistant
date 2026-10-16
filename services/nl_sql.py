"""Natural-language query planning with a strict, read-only SQL compiler."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

from database.connection import db

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BRAZIL_STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

METRICS = {
    "gross_sales", "sales_orders", "placed_orders", "unique_customers",
    "average_order_value", "average_review", "payment_value",
}
DIMENSIONS = {"none", "month", "category", "state", "seller_state", "order_status", "payment_type"}

ALLOWED_DIMENSIONS = {
    "gross_sales": {"none", "month", "category", "state", "seller_state", "order_status"},
    "sales_orders": {"none", "month", "category", "state", "seller_state", "order_status"},
    "placed_orders": {"none", "month", "category", "state", "order_status"},
    "unique_customers": {"none", "month", "category", "state"},
    "average_order_value": {"none", "month", "category", "state"},
    "average_review": {"none", "month", "category", "state"},
    "payment_value": {"none", "month", "state", "payment_type"},
}

METRIC_LABELS = {
    "gross_sales": "Gross item sales (R$)",
    "sales_orders": "Orders with items",
    "placed_orders": "Orders placed",
    "unique_customers": "Unique customers",
    "average_order_value": "Average order value (R$)",
    "average_review": "Average review score (out of 5)",
    "payment_value": "Payment value (R$)",
}


@dataclass(frozen=True)
class QueryPlan:
    metric: str
    dimension: str = "none"
    limit: int = 20
    year: int | None = None
    state: str | None = None


def validate_plan(value: dict[str, Any]) -> QueryPlan:
    """Strictly validate a local or model-produced plan before SQL compilation."""
    metric = value.get("metric")
    dimension = value.get("dimension", "none")
    limit = value.get("limit", 20)
    year = value.get("year")
    state = value.get("state")
    if metric not in METRICS:
        raise ValueError("I couldn't identify a supported measure. Try sales, orders, customers, reviews, payments, or average order value.")
    if dimension not in DIMENSIONS or dimension not in ALLOWED_DIMENSIONS[metric]:
        raise ValueError("That measure and grouping aren't supported together. Try one of the examples shown on this page.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("The result limit must be a whole number from 1 to 100.")
    if year is not None and (type(year) is not int or not 2016 <= year <= 2100):
        raise ValueError("Use a four-digit year from 2016 onward.")
    if state is not None:
        if not isinstance(state, str) or state.strip().upper() not in BRAZIL_STATES:
            raise ValueError("State filters must use a valid two-letter Brazilian state code, such as SP or RJ.")
        state = state.strip().upper()
    return QueryPlan(metric=metric, dimension=dimension, limit=limit, year=year, state=state)


def _local_plan(question: str) -> QueryPlan:
    """Parse common supported business questions without an external model."""
    q = question.casefold()
    if re.search(r"\b(product|sku|item)\b", q) and not re.search(r"\b(category|categories)\b", q):
        raise ValueError("This page groups product performance by category; individual SKU questions aren't supported yet.")

    if re.search(r"\b(review|rating|rated)\b", q):
        metric = "average_review"
    elif re.search(r"\b(payment|payments|installment|paid)\b", q):
        metric = "payment_value"
    elif re.search(r"\b(customer|customers|buyer|buyers)\b", q):
        metric = "unique_customers"
    elif re.search(r"\b(avg|average|mean)\s+(order\s+)?(value|basket|order value)\b|\baov\b", q):
        metric = "average_order_value"
    elif re.search(r"\b(orders?|order count|number of orders)\b", q):
        metric = "placed_orders"
    elif re.search(r"\b(sales|revenue|gross|turnover)\b", q):
        metric = "gross_sales"
    else:
        raise ValueError("I couldn't identify a supported measure. Try sales, orders, customers, reviews, payments, or average order value.")

    if re.search(r"\b(payment type|payment method|by payment|payments by)\b", q):
        dimension = "payment_type"
    elif re.search(r"\b(seller state|seller location)\b", q):
        dimension = "seller_state"
    elif re.search(r"\b(category|categories)\b", q):
        dimension = "category"
    elif re.search(r"\b(state|states|region|regions)\b", q):
        dimension = "state"
    elif re.search(r"\b(status(?:es)?|cancelled|canceled|delivered|order status)\b", q):
        dimension = "order_status"
    elif re.search(r"\b(month|monthly|trend|over time|timeline)\b", q):
        dimension = "month"
    else:
        dimension = "none"

    year_match = re.search(r"\b(20\d{2})\b", q)
    state_match = re.search(r"\b(?:in|from|for)\s+([a-z]{2})\b", q)
    limit_match = re.search(r"\btop\s+(\d{1,3})\b", q)
    return validate_plan({
        "metric": metric,
        "dimension": dimension,
        "limit": int(limit_match.group(1)) if limit_match else (100 if dimension == "month" else 20),
        "year": int(year_match.group(1)) if year_match else None,
        "state": state_match.group(1).upper() if state_match else None,
    })


def _model_plan(question: str, provider: str, api_key: str, model: str) -> QueryPlan:
    """Ask a configured provider for a constrained plan (never for SQL)."""
    system_prompt = (
        "Map the user's BI question to exactly one JSON object with keys metric, dimension, limit, year, state. "
        f"Allowed metric values: {sorted(METRICS)}. Allowed dimension values: {sorted(DIMENSIONS)}. "
        "limit is integer 1..100; year is integer or null; state is a two-letter Brazilian state code or null. "
        "Use null for absent year/state, limit 100 for month groupings and 20 otherwise unless the user asks for top N. Do not produce SQL, explanations, markdown, or extra keys. "
        "Use payment_value for money paid (not revenue); gross_sales for SUM of product item prices excluding freight; "
        "placed_orders for orders, unique_customers for people, and average_order_value for AOV. "
        "Use dimension none if no grouping is requested. If the question cannot be mapped, return metric unsupported."
    )
    payload: dict[str, Any]
    headers = {"Content-Type": "application/json"}
    if provider == "OpenAI API":
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question[:500]},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 160,
        }
        url = "https://api.openai.com/v1/chat/completions"
    elif provider == "Claude API":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        payload = {
            "model": model,
            "max_tokens": 200,
            "system": system_prompt,
            "messages": [{"role": "user", "content": question[:500]}],
        }
        url = "https://api.anthropic.com/v1/messages"
    else:
        raise ValueError("Choose the built-in parser, Claude API, or OpenAI API.")

    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(f"{provider} rejected the API key (HTTP {exc.code}). Check the local secret configuration.") from None
        if exc.code == 429:
            raise RuntimeError(f"{provider} rate or billing limit was reached (HTTP 429). Try the built-in parser or check the provider account.") from None
        raise RuntimeError(f"{provider} request failed with HTTP {exc.code}.") from None
    except (URLError, TimeoutError):
        raise RuntimeError(f"Could not reach {provider}. Check the internet connection and try again.") from None

    if provider == "OpenAI API":
        content = body["choices"][0]["message"]["content"]
    else:
        content = "".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text")
    try:
        plan = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("The selected model returned a plan that wasn't valid JSON. Try again or use the built-in parser.") from None
    return validate_plan(plan)


def create_plan(question: str, provider: str = "Built-in parser", api_key: str = "", model: str = "") -> QueryPlan:
    """Produce a validated plan from a bounded user question."""
    clean = " ".join(question.split())
    if len(clean) < 3:
        raise ValueError("Enter a business question first.")
    if len(clean) > 500:
        raise ValueError("Keep the question under 500 characters.")
    if provider == "Built-in parser":
        return _local_plan(clean)
    if not api_key:
        raise RuntimeError(f"{provider} is not configured. Add its API key to local `.env` or `.streamlit/secrets.toml`.")
    if not model:
        raise RuntimeError(f"Set a model name for {provider} in local configuration.")
    return _model_plan(clean, provider, api_key, model)


def compile_safe_query(plan: QueryPlan) -> tuple[str, dict[str, Any]]:
    """Compile only whitelisted SELECT templates with bound values."""
    plan = validate_plan(plan.__dict__)
    params: dict[str, Any] = {"limit": plan.limit}
    filters: list[str] = []
    cte_sql = ""

    def add_common_filters(order_alias: str = "o", customer_alias: str = "c") -> None:
        if plan.year is not None:
            filters.append(f"EXTRACT(YEAR FROM {order_alias}.order_purchase_timestamp) = :year")
            params["year"] = plan.year
        if plan.state is not None:
            filters.append(f"{customer_alias}.customer_state = :state")
            params["state"] = plan.state

    metric = plan.metric
    dim = plan.dimension
    if metric in {"gross_sales", "sales_orders"}:
        add_common_filters()
        from_sql = """
            FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
            JOIN customers c ON c.customer_id = o.customer_id
            LEFT JOIN products p ON p.product_id = oi.product_id
            LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
            JOIN sellers s ON s.seller_id = oi.seller_id
        """
        value_sql = "SUM(oi.price)" if metric == "gross_sales" else "COUNT(DISTINCT oi.order_id)"
        dimension_expr = {
            "month": "DATE_TRUNC('month', o.order_purchase_timestamp)",
            "category": "COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized')",
            "state": "c.customer_state", "seller_state": "s.seller_state", "order_status": "o.order_status",
        }.get(dim)
    elif metric == "placed_orders":
        add_common_filters()
        from_sql = "FROM orders o JOIN customers c ON c.customer_id = o.customer_id"
        if dim == "category":
            from_sql += " JOIN order_items oi ON oi.order_id = o.order_id LEFT JOIN products p ON p.product_id = oi.product_id LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name"
        value_sql = "COUNT(DISTINCT o.order_id)"
        dimension_expr = {
            "month": "DATE_TRUNC('month', o.order_purchase_timestamp)",
            "category": "COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized')",
            "state": "c.customer_state", "order_status": "o.order_status",
        }.get(dim)
    elif metric == "unique_customers":
        add_common_filters()
        from_sql = "FROM customers c JOIN orders o ON o.customer_id = c.customer_id"
        if dim == "category":
            from_sql += " JOIN order_items oi ON oi.order_id = o.order_id LEFT JOIN products p ON p.product_id = oi.product_id LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name"
        value_sql = "COUNT(DISTINCT c.customer_unique_id)"
        dimension_expr = {
            "month": "DATE_TRUNC('month', o.order_purchase_timestamp)",
            "category": "COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized')",
            "state": "c.customer_state",
        }.get(dim)
    elif metric == "average_order_value":
        add_common_filters("os", "os")
        cte_sql = """WITH order_sales AS (
            SELECT o.order_id, o.order_purchase_timestamp, c.customer_state,
                   SUM(oi.price)::double precision AS gross_sales
            FROM orders o JOIN customers c ON c.customer_id = o.customer_id
            JOIN order_items oi ON oi.order_id = o.order_id
            GROUP BY o.order_id, o.order_purchase_timestamp, c.customer_state
        )"""
        from_sql = "FROM order_sales os"
        if dim == "category":
            from_sql += " JOIN order_items oi ON oi.order_id = os.order_id LEFT JOIN products p ON p.product_id = oi.product_id LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name"
        filters.append("os.gross_sales > 0")
        value_sql = "AVG(os.gross_sales)"
        dimension_expr = {
            "month": "DATE_TRUNC('month', os.order_purchase_timestamp)",
            "category": "COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized')",
            "state": "os.customer_state",
        }.get(dim)
    elif metric == "average_review":
        add_common_filters()
        cte_sql = """WITH review_by_order AS (
            SELECT order_id, AVG(review_score)::double precision AS score
            FROM order_reviews GROUP BY order_id
        )"""
        from_sql = "FROM review_by_order r JOIN orders o ON o.order_id = r.order_id JOIN customers c ON c.customer_id = o.customer_id"
        if dim == "category":
            from_sql += " JOIN (SELECT DISTINCT oi.order_id, COALESCE(ct.product_category_name_english, p.product_category_name, 'Uncategorized') AS category FROM order_items oi LEFT JOIN products p ON p.product_id = oi.product_id LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name) cat ON cat.order_id = o.order_id"
        value_sql = "AVG(r.score)"
        dimension_expr = {
            "month": "DATE_TRUNC('month', o.order_purchase_timestamp)",
            "category": "cat.category", "state": "c.customer_state",
        }.get(dim)
    else:  # payment_value
        add_common_filters()
        from_sql = "FROM order_payments op JOIN orders o ON o.order_id = op.order_id JOIN customers c ON c.customer_id = o.customer_id"
        value_sql = "SUM(op.payment_value)"
        dimension_expr = {
            "month": "DATE_TRUNC('month', o.order_purchase_timestamp)",
            "state": "c.customer_state", "payment_type": "op.payment_type",
        }.get(dim)

    where_sql = " WHERE " + " AND ".join(filters) if filters else ""
    if dimension_expr:
        ordering = "group_value ASC" if dim == "month" else "value DESC"
        sql = f"{cte_sql} SELECT {dimension_expr} AS group_value, {value_sql} AS value {from_sql}{where_sql} GROUP BY 1 ORDER BY {ordering} LIMIT :limit"
    else:
        sql = f"{cte_sql} SELECT {value_sql} AS value {from_sql}{where_sql}"
        params.pop("limit", None)
    return sql, params


def execute_read_only(sql: str, params: dict[str, Any]) -> pd.DataFrame:
    """Execute a compiled aggregate query in a read-only transaction with a time limit."""
    with db.engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '8s'")
            result = pd.read_sql(text(sql), connection, params=params)
            transaction.rollback()
            return result
        except Exception:
            transaction.rollback()
            raise
