"""Searchable order explorer with processing and delivery context."""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.order_analytics import OrderAnalytics


@st.cache_data(ttl=900, show_spinner=False)
def load_filter_options() -> dict:
    return OrderAnalytics().filter_options()


@st.cache_data(ttl=300, show_spinner=False)
def load_overview(start: date, end: date, statuses: tuple, states: tuple, search: str) -> dict:
    return OrderAnalytics().overview(start, end, statuses, states, search)


@st.cache_data(ttl=300, show_spinner=False)
def load_order_page(start: date, end: date, statuses: tuple, states: tuple,
                    search: str, limit: int, offset: int) -> pd.DataFrame:
    return OrderAnalytics().page(start, end, statuses, states, search, limit, offset)


@st.cache_data(ttl=300, show_spinner=False)
def load_order_details(order_id: str) -> dict:
    return OrderAnalytics().details(order_id)


def money(value) -> str:
    return f"R$ {float(value or 0):,.2f}"


def render() -> None:
    set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
    st.title("🧾 Orders")
    st.caption(
        "Search and filter Olist orders, review fulfillment milestones, and inspect the items, "
        "payments, and customer feedback linked to an order. Item value excludes freight."
    )

    if not db.test_connection():
        st.error("Cannot connect to PostgreSQL. Start the database service and check the project `.env` settings.")
        return

    try:
        options = load_filter_options()
    except Exception as exc:
        st.error("The Orders page could not load its filter options from the database.")
        st.caption(f"Diagnostic: {type(exc).__name__}")
        return

    if options["start"] is None or options["end"] is None:
        st.info("There are no dated orders to display yet. Import the Olist data, then reload this page.")
        return

    status_options = tuple(options["statuses"])
    state_options = tuple(options["states"])
    if "orders_search_draft" not in st.session_state:
        st.session_state.orders_search_draft = ""
        st.session_state.orders_status_draft = list(status_options)
        st.session_state.orders_state_draft = list(state_options)
        st.session_state.orders_dates_draft = (options["start"], options["end"])
        st.session_state.orders_filters = {
            "search": "", "statuses": status_options, "states": state_options,
            "start": options["start"], "end": options["end"],
        }

    with st.form("orders_filters_form", border=True):
        st.subheader("Find orders")
        left, right = st.columns(2)
        with left:
            st.text_input("Order or customer ID", key="orders_search_draft",
                          placeholder="Type all or part of an ID")
            selected_statuses = st.multiselect(
                "Order status", options=status_options, key="orders_status_draft"
            )
        with right:
            selected_dates = st.date_input(
                "Purchase date range", min_value=options["start"], max_value=options["end"],
                key="orders_dates_draft",
            )
            selected_states = st.multiselect(
                "Customer state", options=state_options, key="orders_state_draft"
            )
        submitted = st.form_submit_button("Apply filters", type="primary")

    if submitted:
        if not isinstance(selected_dates, (tuple, list)) or len(selected_dates) != 2:
            st.warning("Choose both a start and end date before applying the filters.")
            return
        start_date, end_date = selected_dates
        if start_date > end_date:
            st.warning("The start date must be on or before the end date.")
            return
        st.session_state.orders_filters = {
            "search": st.session_state.orders_search_draft.strip(),
            "statuses": tuple(selected_statuses),
            "states": tuple(selected_states),
            "start": start_date,
            "end": end_date,
        }
        st.session_state.orders_page = 1

    active = st.session_state.orders_filters
    start_date, end_date = active["start"], active["end"]
    statuses, states, search = active["statuses"], active["states"], active["search"]

    try:
        overview = load_overview(start_date, end_date, statuses, states, search)
    except Exception as exc:
        st.error("Could not calculate order summaries. Check that the Olist tables are initialized.")
        st.caption(f"Diagnostic: {type(exc).__name__}")
        return

    summary = overview["summary"]
    total_orders = int(summary["total_orders"] or 0)
    delivered = int(summary["delivered_orders"] or 0)
    delivered_share = (100 * delivered / total_orders) if total_orders else 0.0
    avg_days = summary["avg_delivery_days"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matching orders", f"{total_orders:,}")
    c2.metric("Item value", money(summary["item_value"]), help="Sum of item prices for the matched orders; excludes freight.")
    c3.metric("Delivered share", f"{delivered_share:.1f}%")
    c4.metric("Average delivery", f"{float(avg_days):.1f} days" if avg_days is not None else "n/a")

    st.caption(f"Showing orders purchased from {start_date:%d %b %Y} through {end_date:%d %b %Y}.")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(
            ChartBuilder.funnel(
                ["Placed", "Approved", "Carrier handoff", "Delivered"],
                [total_orders, int(summary["approved_orders"] or 0),
                 int(summary["carrier_handoffs"] or 0), int(summary["customer_deliveries"] or 0)],
                "Order processing milestones",
            ),
            alt="Counts of matched orders with purchase, approval, carrier, and delivery timestamps",
        )
    with chart_right:
        if overview["punctuality"].empty:
            st.info("No completed deliveries with an estimated date match the current filters.")
        else:
            st.plotly_chart(
                ChartBuilder.horizontal_bar(
                    overview["punctuality"], "outcome", "orders", "Delivered orders vs. estimate"
                ),
                alt="Delivered orders grouped by whether they arrived on time, early, late, or had no estimate",
            )

    with st.expander("Order status breakdown"):
        st.plotly_chart(
            ChartBuilder.horizontal_bar(overview["statuses"], "status", "orders", "Orders by status"),
            alt="Number of matched orders in each order status",
        )

    page_size = st.selectbox("Orders per page", [25, 50, 100], index=1, key="orders_page_size")
    max_pages = max(1, (total_orders + page_size - 1) // page_size)
    if st.session_state.get("orders_page", 1) > max_pages:
        st.session_state.orders_page = max_pages
    current_page = st.number_input(
        "Page", min_value=1, max_value=max_pages, step=1, key="orders_page"
    )
    offset = (int(current_page) - 1) * page_size

    st.subheader("Order records")
    try:
        order_page = load_order_page(
            start_date, end_date, statuses, states, search, page_size, offset
        )
    except Exception as exc:
        st.error("Could not load order records for this page.")
        st.caption(f"Diagnostic: {type(exc).__name__}")
        return

    st.caption(f"Page {int(current_page)} of {max_pages} · {total_orders:,} matching orders")
    if order_page.empty:
        st.info("No orders match these filters. Adjust the search or filters and apply them again.")
        return

    st.dataframe(
        order_page,
        hide_index=True,
        column_config={
            "order_id": st.column_config.TextColumn("Order ID"),
            "order_purchase_timestamp": st.column_config.DatetimeColumn("Purchased", format="DD MMM YYYY, HH:mm"),
            "order_status": st.column_config.TextColumn("Status"),
            "customer_unique_id": st.column_config.TextColumn("Customer ID"),
            "customer_state": st.column_config.TextColumn("State"),
            "item_value": st.column_config.NumberColumn("Item value", format="R$ %.2f"),
            "freight_value": st.column_config.NumberColumn("Freight", format="R$ %.2f"),
            "payment_value": st.column_config.NumberColumn("Paid", format="R$ %.2f"),
            "review_score": st.column_config.NumberColumn("Review", format="%.2f"),
            "delivery_days": st.column_config.NumberColumn("Delivery days", format="%.1f"),
            "days_late": st.column_config.NumberColumn("Days vs. estimate", format="%.1f"),
        },
        alt="Filtered orders with purchase, customer state, item and payment totals, reviews, and delivery timing",
    )

    selected_order = st.selectbox(
        "Order details", order_page["order_id"].tolist(), key="orders_detail_id"
    )
    st.subheader(f"Order details · {selected_order}")
    try:
        details = load_order_details(selected_order)
    except Exception as exc:
        st.error("Could not load the selected order details.")
        st.caption(f"Diagnostic: {type(exc).__name__}")
        return

    detail_items, detail_payments = st.columns(2)
    with detail_items:
        st.markdown("**Items and sellers**")
        if details["items"].empty:
            st.info("No item rows are linked to this order.")
        else:
            st.dataframe(details["items"], hide_index=True, alt="Products and sellers in the selected order")
    with detail_payments:
        st.markdown("**Payments**")
        if details["payments"].empty:
            st.info("No payment rows are linked to this order.")
        else:
            st.dataframe(details["payments"], hide_index=True, alt="Payments recorded for the selected order")
    if not details["reviews"].empty:
        st.markdown("**Customer reviews**")
        st.dataframe(details["reviews"], hide_index=True, alt="Reviews recorded for the selected order")


render()
