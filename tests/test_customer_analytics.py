"""
tests/test_customer_analytics.py

WHY THIS FILE EXISTS:
    Confirms Module 10's customer numbers are RIGHT, not merely
    plausible. Every check compares the service against something
    computed a different way: raw SQL, Module 8's KPI service, or a
    from-scratch pandas re-implementation of the trickiest rule
    ("a person's state = state of their most recent order").

    Run manually:  python tests/test_customer_analytics.py
    Or via pytest: pytest tests/test_customer_analytics.py -v
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from database.connection import db  # noqa: E402
from services.customer_analytics import CustomerAnalytics  # noqa: E402
from services.kpi import KPICalculator  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


@pytest.fixture(scope="module")
def ca() -> CustomerAnalytics:
    return CustomerAnalytics()


def _scalar(sql: str, **params):
    with db.engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_customers_are_people_not_orders(ca: CustomerAnalytics) -> None:
    """One row per customer_unique_id; far fewer people than customer_ids."""
    t = ca.customer_table()
    distinct_people = _scalar("SELECT COUNT(DISTINCT customer_unique_id) FROM customers")
    assert len(t) == distinct_people
    assert t["customer_unique_id"].is_unique
    assert len(t) < _scalar("SELECT COUNT(DISTINCT customer_id) FROM customers")


def test_state_counts_add_up_despite_people_who_moved(ca: CustomerAnalytics) -> None:
    """
    39 people appear in several states. Counting each in every state
    would push the state total above the true number of people. Using
    the most-recent-order state must make it add up exactly.
    """
    movers = _scalar("""
        SELECT COUNT(*) FROM (SELECT customer_unique_id FROM customers
        GROUP BY 1 HAVING COUNT(DISTINCT customer_state) > 1) t
    """)
    assert movers > 0, "dataset no longer has movers - this test would prove nothing"

    by_state = ca.by_state()
    assert int(by_state["customers"].sum()) == len(ca.customer_table())
    assert abs(by_state["pct_of_customers"].sum() - 100) < 0.1


def test_state_is_the_state_of_the_most_recent_order(ca: CustomerAnalytics) -> None:
    """
    Independent check: rebuild 'state of most recent order' in pandas
    from the raw tables and compare per-state counts with the service.
    """
    raw = pd.read_sql(
        """SELECT c.customer_unique_id AS uid, c.customer_state AS state,
                  o.order_id, o.order_purchase_timestamp AS ts
           FROM customers c JOIN orders o ON o.customer_id = c.customer_id""",
        db.engine,
    )
    latest = (
        raw.sort_values(["uid", "ts", "order_id"], ascending=[True, False, False])
        .drop_duplicates("uid", keep="first")
    )
    expected = latest["state"].value_counts().sort_index()
    actual = ca.by_state().set_index("state")["customers"].sort_index()
    pd.testing.assert_series_equal(actual, expected, check_names=False, check_dtype=False)


def test_a_specific_mover_is_counted_under_their_latest_state(ca: CustomerAnalytics) -> None:
    """Pick a real person who moved and check them against a direct query."""
    with db.engine.connect() as conn:
        uid = conn.execute(text("""
            SELECT customer_unique_id FROM customers
            GROUP BY 1 HAVING COUNT(DISTINCT customer_state) > 1 ORDER BY 1 LIMIT 1
        """)).scalar()
        expected_state = conn.execute(text("""
            SELECT c.customer_state FROM customers c JOIN orders o ON o.customer_id = c.customer_id
            WHERE c.customer_unique_id = :uid
            ORDER BY o.order_purchase_timestamp DESC, o.order_id DESC LIMIT 1
        """), {"uid": uid}).scalar()
    row = ca.customer_table().set_index("customer_unique_id").loc[uid]
    assert row["state"] == expected_state


def test_revenue_reconciles_with_module_8_kpis(ca: CustomerAnalytics) -> None:
    """Per-state revenue and per-person spend must both sum to Module 8's total_revenue."""
    kpi_revenue = KPICalculator().calculate().total_revenue
    raw_revenue = float(_scalar("SELECT SUM(price) FROM order_items"))
    assert abs(float(ca.by_state()["revenue"].sum()) - kpi_revenue) < 1.0
    assert abs(float(ca.customer_table()["spend"].sum()) - raw_revenue) < 0.01


def test_repeat_rate_matches_module_8_kpi(ca: CustomerAnalytics) -> None:
    assert ca.summary().repeat_rate_pct == KPICalculator().calculate().repeat_customer_rate_pct


def test_paying_plus_zero_spend_equals_all_customers(ca: CustomerAnalytics) -> None:
    s = ca.summary()
    assert s.paying_customers + s.zero_spend_customers == s.unique_customers
    assert s.zero_spend_customers > 0
    assert s.one_time_customers + s.repeat_customers == s.unique_customers


def test_spend_stats_match_independent_sql(ca: CustomerAnalytics) -> None:
    s = ca.summary()
    avg, med, mx = None, None, None
    with db.engine.connect() as conn:
        avg, med, mx = conn.execute(text("""
            WITH t AS (SELECT SUM(oi.price) AS total
                       FROM customers c JOIN orders o ON o.customer_id = c.customer_id
                       JOIN order_items oi ON oi.order_id = o.order_id
                       GROUP BY c.customer_unique_id)
            SELECT AVG(total), PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total), MAX(total) FROM t
        """)).fetchone()
    assert abs(s.avg_spend - float(avg)) < 0.01
    assert abs(s.median_spend - float(med)) < 0.01
    assert abs(s.max_spend - float(mx)) < 0.01
    assert s.median_spend < s.avg_spend, "spend is right-skewed: median should sit below the mean"


def test_orders_per_customer_distribution(ca: CustomerAnalytics) -> None:
    dist = ca.orders_per_customer()
    assert list(dist["orders_placed"]) == ["1", "2", "3", "4+"]
    assert int(dist["customers"].sum()) == len(ca.customer_table())
    one = _scalar("""
        SELECT COUNT(*) FROM (SELECT c.customer_unique_id FROM customers c
        JOIN orders o ON o.customer_id = c.customer_id
        GROUP BY 1 HAVING COUNT(*) = 1) t
    """)
    assert int(dist.loc[dist["orders_placed"] == "1", "customers"].iloc[0]) == one


def test_new_vs_returning_each_person_is_new_exactly_once(ca: CustomerAnalytics) -> None:
    monthly = ca.new_vs_returning_monthly()
    assert int(monthly["new_customers"].sum()) == len(ca.customer_table())
    assert int(monthly["returning_customers"].sum()) > 0
    # First month can't have anyone 'returning'.
    assert int(monthly.iloc[0]["returning_customers"]) == 0


def test_new_plus_returning_equals_active_people_each_month(ca: CustomerAnalytics) -> None:
    """Independent SQL: distinct people active per month must equal new + returning."""
    monthly = ca.new_vs_returning_monthly().set_index("month")
    active = pd.read_sql(
        """SELECT DATE_TRUNC('month', o.order_purchase_timestamp) AS month,
                  COUNT(DISTINCT c.customer_unique_id) AS active
           FROM customers c JOIN orders o ON o.customer_id = c.customer_id
           GROUP BY 1 ORDER BY 1""",
        db.engine,
    ).set_index("month")["active"]
    combined = (monthly["new_customers"] + monthly["returning_customers"]).astype("int64")
    pd.testing.assert_series_equal(combined, active.astype("int64"), check_names=False)


def test_quick_followup_numbers_are_internally_consistent(ca: CustomerAnalytics) -> None:
    f = ca.quick_followup_analysis()
    s = ca.summary()
    assert f["different_sellers"] + f["shares_a_seller"] + f["no_items"] == f["single_session_repeaters"]
    # People with 2+ orders who never came back after 24h == repeaters - returners.
    assert f["single_session_repeaters"] == s.repeat_customers - s.returned_after_24h_customers
    assert s.returned_after_24h_customers <= s.repeat_customers


def test_top_customers_sorted_and_consistent(ca: CustomerAnalytics) -> None:
    top = ca.top_customers(10)
    assert len(top) == 10
    assert top["spend"].is_monotonic_decreasing
    assert top.iloc[0]["spend"] == ca.summary().max_spend


def test_top_cities_keep_same_named_cities_in_different_states_apart(ca: CustomerAnalytics) -> None:
    shared_names = _scalar("""
        SELECT COUNT(*) FROM (SELECT customer_city FROM customers
        GROUP BY 1 HAVING COUNT(DISTINCT customer_state) > 1) t
    """)
    assert shared_names > 0, "no shared city names - this test would prove nothing"
    cities = ca.top_cities(50)
    assert not cities.duplicated(["city", "state"]).any()
    assert cities["label"].is_unique
    assert cities["customers"].is_monotonic_decreasing


def test_summary_is_json_serialisable(ca: CustomerAnalytics) -> None:
    """Plain Python types only - numpy scalars break json.dumps (see Module 6)."""
    json.dumps(asdict(ca.summary()))
    json.dumps(ca.quick_followup_analysis())


if __name__ == "__main__":
    logger.info("Running standalone customer analytics check...")
    sys.exit(pytest.main([__file__, "-q"]))
