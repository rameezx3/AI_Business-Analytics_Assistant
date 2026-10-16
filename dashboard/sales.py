"""
dashboard/sales.py

Sales Analytics page (Module 11) - replaces the Module 7 placeholder.
Presentation only: numbers come from services/sales_analytics.py, charts
from services/charts.py. No SQL lives here.

Every figure in the explanatory text is computed from the data at render
time, never hard-coded, so the text cannot drift out of date.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.sales_analytics import SalesAnalytics


def _money(x: float) -> str:
    return f"R$ {x:,.2f}"


@st.cache_data(ttl=3600)
def load_sales_data() -> dict:
    """Everything except the date-range-dependent daily series. Cached one hour."""
    sa = SalesAnalytics()
    monthly = sa.monthly_sales()
    order_values = sa.order_values()
    matrix = sa.weekday_hour_matrix()
    return {
        "summary": sa.summary(),
        "monthly": monthly,
        "categories": sa.sales_by_category(),
        "states": sa.sales_by_state(),
        "payments": sa.payment_mix(),
        "installments": sa.credit_card_installments(),
        "order_values": order_values,
        "order_value_stats": sa.order_value_summary(order_values),
        "matrix": matrix,
        "demand": sa.demand_pattern(matrix),
        "top_days": sa.top_days(5),
        "window": sa.reliable_window(monthly=monthly),
    }


@st.cache_data(ttl=900)
def load_daily(start: date, end: date) -> pd.DataFrame:
    return SalesAnalytics().daily_sales(start, end)


def render() -> None:
    light_theme = st.session_state.get("light_theme", False)
    set_chart_theme("light" if light_theme else "dark")
    st.title("💰 Sales Analytics")
    st.caption(
        "Gross sales = the price of items sold, across all orders (excludes shipping). "
        "It matches the Total Revenue on the Home page."
    )

    if not db.test_connection():
        st.error(
            "⚠️ Cannot connect to the database. Check that PostgreSQL is "
            "running and your `.env` file has the correct credentials, "
            "then reload this page. (See the Settings page for details.)"
        )
        return

    d = load_sales_data()
    s = d["summary"]
    monthly = d["monthly"]

    r1 = st.columns(4)
    r1[0].metric("Gross Sales", _money(s.gross_sales))
    r1[1].metric("Delivered Share", f"{s.delivered_share_pct}%")
    r1[2].metric("Orders With Sales", f"{s.sales_orders:,}")
    r1[3].metric("Avg Order Value", _money(s.avg_order_value))

    r2 = st.columns(4)
    r2[0].metric("Items per Order", f"{s.avg_items_per_order}")
    r2[1].metric("Shipping as % of Sales", f"{s.freight_pct_of_sales}%")
    if s.yoy_growth_pct is not None:
        r2[2].metric("Year-over-Year Growth", f"{s.yoy_growth_pct:+.1f}%")
    else:
        r2[2].metric("Year-over-Year Growth", "n/a")
    r2[3].metric("Best Month", s.best_month, help=f"Gross sales {_money(s.best_month_sales)}")

    st.caption(
        f"Year-over-year compares the {s.yoy_months_compared} months that are complete in both years "
        f"(same months each year, so a part-year can't distort it)."
    )
    st.info(
        f"**{s.delivered_share_pct}%** of gross sales is in delivered orders. "
        f"{_money(s.canceled_sales)} is in cancelled/unavailable orders and "
        f"{_money(s.in_progress_sales)} is in orders not yet delivered."
    )

    # ---------------------------------------------------------------- trend
    st.subheader("How are sales trending?")
    n_months = len(monthly)
    n_zero = int((monthly["orders_placed"] == 0).sum())
    st.info(
        f"Only **{s.reliable_months} of {n_months}** calendar months "
        f"({s.reliable_window_start} to {s.reliable_window_end}) are full trading months - the others are "
        f"the ramp-up before and the data cutoff after, with very few orders"
        + (f" ({n_zero} month{'s' if n_zero != 1 else ''} with no orders at all)" if n_zero else "")
        + ". Growth figures only compare full trading months."
    )

    trend = monthly.copy()
    trend["Month type"] = trend["reliable"].map(
        {True: "Full trading month", False: "Ramp-up / cutoff (few orders)"}
    )
    st.plotly_chart(
        ChartBuilder.bar(trend, "month", "gross_sales", "Gross Sales by Month", color="Month type"),
        width="stretch",
    )

    full = monthly[monthly["reliable"]]
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            ChartBuilder.line(full, "month", "avg_order_value", "Average Order Value by Month (R$)",
                              y_label="R$ per order"),
            width="stretch",
        )
    with right:
        growth = full[full["mom_growth_pct"].notna()]
        st.plotly_chart(
            ChartBuilder.bar(growth, "month", "mom_growth_pct", "Month-over-Month Growth in Gross Sales (%)"),
            width="stretch",
        )

    # ---------------------------------------------------------------- daily
    st.markdown("**Daily sales**")
    window_start, window_end = d["window"]
    top_days = d["top_days"]
    peak = top_days.iloc[0]
    peak_day = peak["day"].date()
    runner_up = float(top_days.iloc[1]["gross_sales"])
    st.caption(
        f"Biggest day ever: **{peak_day:%d %b %Y}** - {_money(float(peak['gross_sales']))} from "
        f"{int(peak['sales_orders']):,} orders, {float(peak['gross_sales']) / runner_up:.1f}x the next-best day. "
        f"The picker below starts on the 61 days around it."
    )
    default_start = max(window_start, peak_day - timedelta(days=30))
    default_end = min(window_end, peak_day + timedelta(days=30))
    picked = st.date_input(
        "Date range", value=(default_start, default_end),
        min_value=window_start, max_value=window_end,
    )
    if isinstance(picked, tuple) and len(picked) == 2:
        daily = load_daily(picked[0], picked[1])
        st.plotly_chart(
            ChartBuilder.line(daily, "day", "gross_sales",
                              f"Daily Gross Sales, {picked[0]:%d %b %Y} to {picked[1]:%d %b %Y}",
                              y_label="R$"),
            width="stretch",
        )
    else:
        st.info("Pick an end date to draw the chart.")
        st.plotly_chart(ChartBuilder.line(pd.DataFrame({"day": [], "gross_sales": []}), "day", "gross_sales",
                                          "Daily Gross Sales"), width="stretch")

    # ------------------------------------------------------ what & where
    st.subheader("What sells, and where?")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            ChartBuilder.horizontal_bar(d["categories"], "category", "gross_sales",
                                        "Top 10 Categories by Gross Sales", top_n=10),
            width="stretch",
        )
    with right:
        st.plotly_chart(
            ChartBuilder.horizontal_bar(d["states"], "state", "gross_sales",
                                        "Top 10 States by Gross Sales", top_n=10),
            width="stretch",
        )
    states = d["states"]
    top_state = states.iloc[0]
    far = states[states["orders"] >= 100].sort_values("freight_pct", ascending=False).iloc[0]
    st.caption(
        f"{top_state['state']} alone is {top_state['pct_of_sales']}% of sales. Shipping weighs most on "
        f"{far['state']}, where it equals {far['freight_pct']}% of item sales "
        f"(vs {float(states.loc[states['state'] == top_state['state'], 'freight_pct'].iloc[0])}% in {top_state['state']}) "
        f"- among states with 100+ orders."
    )

    # -------------------------------------------------------- payments
    st.subheader("How do customers pay?")
    st.info(
        f"Payments total {_money(s.payments_total)}, more than gross sales plus shipping, because "
        f"{_money(s.payments_on_orders_without_items)} was paid on orders that contain no items "
        f"(mostly cancelled or unavailable orders), and some card payments include installment interest. "
        f"The charts below show **money paid**, not revenue."
    )
    left, right = st.columns(2)
    pay = d["payments"]
    with left:
        st.plotly_chart(
            ChartBuilder.pie(pay[pay["payment_value"] > 0], "payment_type", "payment_value",
                             "Money Paid by Payment Method"),
            width="stretch",
        )
    with right:
        st.plotly_chart(
            ChartBuilder.bar(d["installments"], "installments", "payment_value",
                             "Credit-Card Money Paid by Number of Installments"),
            width="stretch",
        )

    # ----------------------------------------------------- order values
    st.subheader("How big are orders?")
    ov = d["order_value_stats"]
    st.caption(
        f"Median order {_money(ov['median'])}, average {_money(ov['mean'])}, 90th percentile "
        f"{_money(ov['p90'])}, 99th percentile {_money(ov['p99'])}, largest {_money(ov['max'])}."
    )
    st.plotly_chart(
        ChartBuilder.histogram(d["order_values"], "order_value", "Order Value Distribution (log scale)",
                               log_x=True),
        width="stretch",
    )

    # ---------------------------------------------------- demand rhythm
    st.subheader("When do customers buy?")
    p = d["demand"]
    st.caption(
        f"Busiest weekday: {p['busiest_weekday']} ({p['busiest_weekday_orders']:,} orders). "
        f"Quietest: {p['quietest_weekday']} ({p['quietest_weekday_orders']:,}). "
        f"Busiest hour: {p['busiest_hour']}:00. Weekends are {p['weekend_share_pct']}% of orders. "
        f"Times are as recorded in the dataset (no timezone is stated)."
    )
    st.plotly_chart(
        ChartBuilder.heatmap(d["matrix"], "Orders by Weekday and Hour", zmin=None, zmax=None,
                             color_scale="Blues", show_values=False),
        width="stretch",
    )

    with st.expander("Monthly detail table"):
        table = monthly.rename(columns={
            "month": "Month", "orders_placed": "Orders placed", "sales_orders": "Orders with sales",
            "gross_sales": "Gross sales (R$)", "delivered_sales": "Delivered sales (R$)",
            "avg_order_value": "AOV (R$)", "reliable": "Full trading month",
            "mom_growth_pct": "MoM %", "yoy_growth_pct": "YoY %",
        })[["Month", "Orders placed", "Orders with sales", "Gross sales (R$)", "Delivered sales (R$)",
            "AOV (R$)", "Full trading month", "MoM %", "YoY %"]]
        table["Month"] = table["Month"].dt.strftime("%Y-%m")
        st.dataframe(table, hide_index=True, width="stretch")


render()
