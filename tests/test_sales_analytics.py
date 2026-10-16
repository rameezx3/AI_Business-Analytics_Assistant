"""
tests/test_sales_analytics.py

WHY THIS FILE EXISTS:
    Confirms Module 11's sales numbers are RIGHT, not just plausible.
    Each check compares the service against something computed a
    different way (raw SQL, Module 8's KPI service). A few tests lock in
    claims made in the module's docstring - e.g. that most of the gap
    between payments and sales is money paid on orders with no items -
    so the documentation can't silently become false.

    These tests do not depend on whether Module 4's cleaning has run.

    Run manually:  python tests/test_sales_analytics.py
    Or via pytest: pytest tests/test_sales_analytics.py -v
"""

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from database.connection import db  # noqa: E402
from services.kpi import KPICalculator  # noqa: E402
from services.sales_analytics import WEEKDAYS, SalesAnalytics  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


@pytest.fixture(scope="module")
def sa() -> SalesAnalytics:
    return SalesAnalytics()


def _scalar(sql: str, **params):
    with db.engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _month_sales(year: int, month: int) -> float:
    return float(_scalar("""
        SELECT COALESCE(SUM(oi.price), 0) FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
        WHERE DATE_TRUNC('month', o.order_purchase_timestamp) = make_date(:y, :m, 1)
    """, y=year, m=month))


# ----------------------------------------------------------------- monthly trend

def test_monthly_series_has_every_calendar_month_including_the_empty_one(sa: SalesAnalytics) -> None:
    """November 2016 has no orders; it must appear as a zero row, not vanish."""
    m = sa.monthly_sales()
    gaps = m["month"].diff().dropna().dt.days
    assert gaps.between(28, 31).all(), "months are not consecutive"
    nov = m[m["month"] == pd.Timestamp("2016-11-01")]
    assert len(nov) == 1, "November 2016 missing from the series"
    assert int(nov["orders_placed"].iloc[0]) == 0 and float(nov["gross_sales"].iloc[0]) == 0.0
    assert _scalar("""SELECT COUNT(*) FROM orders
                      WHERE DATE_TRUNC('month', order_purchase_timestamp) = '2016-11-01'""") == 0


def test_monthly_totals_reconcile_with_raw_tables(sa: SalesAnalytics) -> None:
    m = sa.monthly_sales()
    assert abs(m["gross_sales"].sum() - float(_scalar("SELECT SUM(price) FROM order_items"))) < 0.5
    assert int(m["orders_placed"].sum()) == _scalar("SELECT COUNT(*) FROM orders")
    assert int(m["sales_orders"].sum()) == _scalar("SELECT COUNT(DISTINCT order_id) FROM order_items")
    assert int(m["items"].sum()) == _scalar("SELECT COUNT(*) FROM order_items")
    assert (m["delivered_sales"] <= m["gross_sales"] + 0.01).all()


def test_reliable_months_are_the_twenty_real_trading_months(sa: SalesAnalytics) -> None:
    m = sa.monthly_sales()
    reliable = m.loc[m["reliable"], "month"]
    assert len(reliable) == 20
    assert reliable.min() == pd.Timestamp("2017-01-01") and reliable.max() == pd.Timestamp("2018-08-01")
    # the unreliable edge months the module warns about
    for bad in ["2016-09-01", "2016-10-01", "2016-11-01", "2016-12-01", "2018-09-01", "2018-10-01"]:
        assert not bool(m.loc[m["month"] == pd.Timestamp(bad), "reliable"].iloc[0]), bad
    # the threshold is a real parameter, not decoration
    loose = sa.monthly_sales(min_orders=1)
    assert loose["reliable"].sum() > m["reliable"].sum()


def test_growth_matches_hand_calculation_and_respects_reliability(sa: SalesAnalytics) -> None:
    m = sa.monthly_sales().set_index("month")
    jan, feb = _month_sales(2017, 1), _month_sales(2017, 2)
    assert m.loc["2017-02-01", "mom_growth_pct"] == round(100 * (feb / jan - 1), 1)
    # Jan 2017 follows Dec 2016 (1 order): comparing against it would be meaningless.
    assert pd.isna(m.loc["2017-01-01", "mom_growth_pct"])
    # Unreliable months never get a growth figure.
    assert pd.isna(m.loc["2016-12-01", "mom_growth_pct"])
    assert pd.isna(m.loc["2018-09-01", "mom_growth_pct"])

    mar17, mar18 = _month_sales(2017, 3), _month_sales(2018, 3)
    assert m.loc["2018-03-01", "yoy_growth_pct"] == round(100 * (mar18 / mar17 - 1), 1)
    assert pd.isna(m.loc["2017-12-01", "yoy_growth_pct"]), "no reliable Dec 2016 to compare against"


# ------------------------------------------------------------------- summary

def test_summary_reconciles_with_raw_data_and_module_8(sa: SalesAnalytics) -> None:
    s = sa.summary()
    kpi = KPICalculator().calculate()
    assert abs(s.gross_sales - float(_scalar("SELECT SUM(price) FROM order_items"))) < 0.01
    assert abs(s.gross_sales - kpi.total_revenue) < 0.01
    assert s.avg_order_value == kpi.average_order_value, "AOV must be one definition across the app"
    assert s.sales_orders == _scalar("SELECT COUNT(DISTINCT order_id) FROM order_items")
    delivered = float(_scalar("""SELECT SUM(oi.price) FROM order_items oi
                                 JOIN orders o ON o.order_id = oi.order_id WHERE o.order_status = 'delivered'"""))
    assert abs(s.delivered_sales - delivered) < 0.01
    assert abs(s.delivered_sales + s.canceled_sales + s.in_progress_sales - s.gross_sales) < 0.02
    assert s.in_progress_sales > 0 and s.canceled_sales > 0


def test_year_over_year_compares_the_same_months_in_both_years(sa: SalesAnalytics) -> None:
    s = sa.summary()
    cur = float(_scalar("""SELECT SUM(oi.price) FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
                           WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-09-01'"""))
    prev = float(_scalar("""SELECT SUM(oi.price) FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
                            WHERE o.order_purchase_timestamp >= '2017-01-01' AND o.order_purchase_timestamp < '2017-09-01'"""))
    assert s.yoy_months_compared == 8
    assert s.yoy_growth_pct == round(100 * (cur / prev - 1), 1)


def test_best_month_is_the_peak_reliable_month(sa: SalesAnalytics) -> None:
    s = sa.summary()
    m = sa.monthly_sales()
    rel = m[m["reliable"]]
    assert s.best_month_sales == float(rel["gross_sales"].max())
    assert abs(s.best_month_sales - _month_sales(int(s.best_month[:4]), int(s.best_month[5:]))) < 0.01


def test_payment_gap_is_mostly_money_paid_on_orders_without_items(sa: SalesAnalytics) -> None:
    """
    Locks in the docstring claim: payments exceed items+freight mainly
    because of payments on orders that have no items at all.
    """
    s = sa.summary()
    independent = float(_scalar("""
        SELECT COALESCE(SUM(p.payment_value), 0) FROM order_payments p
        WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = p.order_id)
    """))
    assert abs(s.payments_on_orders_without_items - independent) < 0.01
    assert abs(s.payments_total - float(_scalar("SELECT SUM(payment_value) FROM order_payments"))) < 0.01

    gap = s.payments_total - (s.gross_sales + s.freight_total)
    assert gap > 0
    assert s.payments_on_orders_without_items / gap > 0.95, "documented claim ('most of the gap') no longer holds"


# ---------------------------------------------------------------- breakdowns

def test_category_sales_add_up_to_gross_sales(sa: SalesAnalytics) -> None:
    cats = sa.sales_by_category()
    gross = float(_scalar("SELECT SUM(price) FROM order_items"))
    assert abs(cats["gross_sales"].sum() - gross) < 1.0
    assert abs(cats["pct_of_sales"].sum() - 100) < 0.5
    assert cats["category"].is_unique
    assert cats["gross_sales"].is_monotonic_decreasing
    assert int(cats["units"].sum()) == _scalar("SELECT COUNT(*) FROM order_items")
    top = pd.read_sql("""
        SELECT COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS c
        FROM order_items oi JOIN products p ON p.product_id = oi.product_id
        LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
        GROUP BY 1 ORDER BY SUM(oi.price) DESC LIMIT 1""", db.engine)["c"].iloc[0]
    assert cats.iloc[0]["category"] == top
    assert len(sa.sales_by_category(top_n=5)) == 5


def test_state_sales_add_up_to_gross_sales(sa: SalesAnalytics) -> None:
    st = sa.sales_by_state()
    s = sa.summary()
    assert abs(st["gross_sales"].sum() - s.gross_sales) < 0.5
    assert int(st["orders"].sum()) == s.sales_orders
    assert abs(st["freight"].sum() - s.freight_total) < 0.5
    assert len(st) == 27 and st["state"].is_unique
    sp = st[st["state"] == "SP"].iloc[0]
    assert abs(sp["avg_order_value"] - sp["gross_sales"] / sp["orders"]) < 0.01


def test_payment_mix_adds_up_and_credit_card_dominates(sa: SalesAnalytics) -> None:
    mix = sa.payment_mix()
    assert abs(mix["payment_value"].sum() - sa.summary().payments_total) < 0.5
    assert abs(mix["pct_of_value"].sum() - 100) < 0.1
    assert mix.iloc[0]["payment_type"] == "credit_card"
    assert int(mix["payments"].sum()) == _scalar("SELECT COUNT(*) FROM order_payments")


def test_credit_card_installment_buckets_cover_every_card_payment(sa: SalesAnalytics) -> None:
    inst = sa.credit_card_installments()
    assert list(inst["installments"]) == ["1x", "2-3x", "4-6x", "7-10x", "11x+"]
    assert int(inst["payments"].sum()) == _scalar("SELECT COUNT(*) FROM order_payments WHERE payment_type = 'credit_card'")
    card_value = float(_scalar("SELECT SUM(payment_value) FROM order_payments WHERE payment_type = 'credit_card'"))
    assert abs(inst["payment_value"].sum() - card_value) < 0.5
    # the 2 zero-installment payments (flagged in Module 5) must not be lost
    zero = _scalar("SELECT COUNT(*) FROM order_payments WHERE payment_type = 'credit_card' AND payment_installments = 0")
    one = _scalar("SELECT COUNT(*) FROM order_payments WHERE payment_type = 'credit_card' AND payment_installments = 1")
    assert int(inst.loc[inst["installments"] == "1x", "payments"].iloc[0]) == zero + one


def test_order_values(sa: SalesAnalytics) -> None:
    ov = sa.order_values()
    s = sa.summary()
    assert len(ov) == s.sales_orders and ov["order_id"].is_unique
    assert abs(ov["order_value"].sum() - s.gross_sales) < 0.01
    stats = sa.order_value_summary()
    assert stats["mean"] == s.avg_order_value
    assert stats["median"] < stats["mean"] < stats["p99"] <= stats["max"]


# ------------------------------------------------------------ demand rhythm

def test_weekday_hour_matrix_matches_raw_counts(sa: SalesAnalytics) -> None:
    m = sa.weekday_hour_matrix()
    assert m.shape == (7, 24) and list(m.index) == WEEKDAYS and list(m.columns) == list(range(24))
    assert int(m.to_numpy().sum()) == _scalar("SELECT COUNT(*) FROM orders")
    monday_16h = _scalar("""SELECT COUNT(*) FROM orders
                            WHERE EXTRACT(DOW FROM order_purchase_timestamp) = 1
                              AND EXTRACT(HOUR FROM order_purchase_timestamp) = 16""")
    assert int(m.loc["Monday", 16]) == monday_16h
    sunday_3h = _scalar("""SELECT COUNT(*) FROM orders
                           WHERE EXTRACT(DOW FROM order_purchase_timestamp) = 0
                             AND EXTRACT(HOUR FROM order_purchase_timestamp) = 3""")
    assert int(m.loc["Sunday", 3]) == sunday_3h


def test_demand_pattern_matches_independent_sql(sa: SalesAnalytics) -> None:
    p = sa.demand_pattern()
    weekend = _scalar("""SELECT COUNT(*) FROM orders
                         WHERE EXTRACT(DOW FROM order_purchase_timestamp) IN (0, 6)""")
    total = _scalar("SELECT COUNT(*) FROM orders")
    assert p["weekend_share_pct"] == round(100 * weekend / total, 1)
    assert p["total_orders"] == total
    assert p["busiest_weekday_orders"] > p["quietest_weekday_orders"]
    assert p["quietest_weekday"] in ("Saturday", "Sunday")


# ------------------------------------------------------------------ daily

def test_daily_sales_is_continuous_and_zero_filled(sa: SalesAnalytics) -> None:
    empty_month = sa.daily_sales(date(2016, 11, 1), date(2016, 11, 30))
    assert len(empty_month) == 30
    assert (empty_month["gross_sales"] == 0).all() and (empty_month["sales_orders"] == 0).all()

    nov17 = sa.daily_sales(date(2017, 11, 1), date(2017, 11, 30))
    assert len(nov17) == 30
    assert nov17["day"].diff().dropna().dt.days.eq(1).all()
    assert abs(nov17["gross_sales"].sum() - _month_sales(2017, 11)) < 0.5


def test_daily_sales_over_the_reliable_window_matches_monthly_totals(sa: SalesAnalytics) -> None:
    start, end = sa.reliable_window()
    assert (start, end) == (date(2017, 1, 1), date(2018, 8, 31))
    daily = sa.daily_sales(start, end)
    monthly = sa.monthly_sales()
    expected = monthly.loc[monthly["reliable"], "gross_sales"].sum()
    assert abs(daily["gross_sales"].sum() - expected) < 0.5


def test_top_days_sorted_and_peak_is_independently_confirmed(sa: SalesAnalytics) -> None:
    top = sa.top_days(5)
    assert len(top) == 5 and top["gross_sales"].is_monotonic_decreasing
    day = top.iloc[0]["day"].date()
    expected = float(_scalar("""SELECT SUM(oi.price) FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
                                WHERE o.order_purchase_timestamp::date = :d""", d=day))
    assert abs(top.iloc[0]["gross_sales"] - expected) < 0.01
    assert top.iloc[0]["gross_sales"] > 2 * top.iloc[1]["gross_sales"], "peak day should stand far above the rest"


def test_summary_is_json_serialisable(sa: SalesAnalytics) -> None:
    json.dumps(asdict(sa.summary()))
    json.dumps(sa.demand_pattern())
    json.dumps(sa.order_value_summary())


if __name__ == "__main__":
    logger.info("Running standalone sales analytics check...")
    sys.exit(pytest.main([__file__, "-q"]))
