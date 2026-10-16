"""
dashboard/customers.py

Customer Analytics page (Module 10) - replaces the Module 7 placeholder.
Presentation only: every number comes from services/customer_analytics.py,
every chart is built by services/charts.py (Module 9). No SQL lives here.

Every figure quoted in the explanatory text is computed from the data at
render time, never hard-coded, so the text can't drift out of date if the
data is refreshed.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.customer_analytics import CustomerAnalytics


@st.cache_data(ttl=3600)
def load_customer_data() -> dict:
    """Everything this page needs, built from ONE consistent customer snapshot. Cached one hour."""
    ca = CustomerAnalytics()
    table = ca.customer_table()
    return {
        "summary": ca.summary(),
        "orders_per_customer": ca.orders_per_customer(),
        "by_state": ca.by_state(),
        "top_cities": ca.top_cities(10),
        "monthly": ca.new_vs_returning_monthly(),
        "top_customers": ca.top_customers(10),
        "spend": table.loc[table["spend"] > 0, ["spend"]],
        "followup": ca.quick_followup_analysis(),
    }


def render() -> None:
    light_theme = st.session_state.get("light_theme", False)
    set_chart_theme("light" if light_theme else "dark")
    st.title("👥 Customer Analytics")
    st.caption(
        "A customer here is a real person (`customer_unique_id`), not an order - "
        "the same person can appear under several order-level customer IDs."
    )

    if not db.test_connection():
        st.error(
            "⚠️ Cannot connect to the database. Check that PostgreSQL is "
            "running and your `.env` file has the correct credentials, "
            "then reload this page. (See the Settings page for details.)"
        )
        return

    data = load_customer_data()
    s = data["summary"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Unique Customers", f"{s.unique_customers:,}")
    c2.metric("Paying Customers", f"{s.paying_customers:,}")
    c3.metric("Avg Spend (paying)", f"R$ {s.avg_spend:,.2f}")
    c4.metric("Median Spend (paying)", f"R$ {s.median_spend:,.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Repeat Rate (2+ orders)", f"{s.repeat_rate_pct}%")
    c6.metric("Returned After 24h", f"{s.returned_after_24h_rate_pct}%")
    c7.metric("Avg Orders / Customer", f"{s.avg_orders_per_customer}")
    c8.metric("Top 1% Revenue Share", f"{s.top_1pct_revenue_share_pct}%")

    # ---- Are customers coming back? ----
    st.subheader("Are customers coming back?")
    f = data["followup"]
    only_quick = f["single_session_repeaters"]
    if s.repeat_customers:
        st.info(
            f"**{s.repeat_rate_pct}%** of customers ordered more than once - but "
            f"**{only_quick:,}** of those **{s.repeat_customers:,}** repeaters placed all their "
            f"orders within 24 hours of their first. For those, the two orders involved different "
            f"sellers in **{f['different_sellers']:,}** cases and a shared seller in "
            f"**{f['shares_a_seller']:,}**, which suggests many were one shopping trip split into "
            f"several orders rather than a real return visit. The stricter *Returned After 24h* "
            f"rate (**{s.returned_after_24h_rate_pct}%**) is the better loyalty measure."
        )
        if s.median_days_to_return is not None:
            st.caption(
                f"People who did return after 24h took a median of {s.median_days_to_return} days "
                f"(mean {s.mean_days_to_return}) - the gap is long and highly skewed."
            )

    left, right = st.columns(2)
    with left:
        fig = ChartBuilder.stacked_bar(
            data["monthly"], "month", ["new_customers", "returning_customers"],
            "Active Customers per Month: New vs Returning",
        )
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = ChartBuilder.bar(data["orders_per_customer"], "orders_placed", "customers",
                               "Customers by Number of Orders Placed")
        st.plotly_chart(fig, width="stretch")

    # ---- Where are they? ----
    st.subheader("Where are customers?")
    st.caption("Each person is counted once, in the state of their most recent order.")
    left, right = st.columns(2)
    with left:
        fig = ChartBuilder.horizontal_bar(data["by_state"], "state", "customers",
                                          "Top 10 States by Customers", top_n=10)
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = ChartBuilder.horizontal_bar(data["top_cities"], "label", "customers",
                                          "Top 10 Cities by Customers")
        st.plotly_chart(fig, width="stretch")

    # ---- How much do they spend? ----
    st.subheader("How much do customers spend?")
    st.caption(
        f"Spend covers paying customers only; {s.zero_spend_customers:,} people had no "
        f"purchased items (all their orders were cancelled or unavailable). "
        f"The top 1% of paying customers account for {s.top_1pct_revenue_share_pct}% of revenue."
    )
    fig = ChartBuilder.histogram(data["spend"], "spend", "Lifetime Spend per Paying Customer (log scale)",
                                 log_x=True)
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Top 10 customers by lifetime spend**")
    top = data["top_customers"].rename(columns={
        "customer_unique_id": "Customer ID", "state": "State", "orders": "Orders", "spend": "Spend (R$)",
    })
    st.dataframe(top, hide_index=True, width="stretch")

    with st.expander("State breakdown (all states)"):
        table = data["by_state"].rename(columns={
            "state": "State", "customers": "Customers", "paying_customers": "Paying",
            "revenue": "Revenue (R$)", "pct_of_customers": "% of Customers", "avg_spend": "Avg Spend (R$)",
        })
        st.dataframe(table, hide_index=True, width="stretch")


render()
