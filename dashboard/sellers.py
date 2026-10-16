"""Module 14: seller performance analytics."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.seller_analytics import SellerAnalytics


@st.cache_data(ttl=1800)
def load_seller_performance():
    return SellerAnalytics().performance()


@st.cache_data(ttl=1800)
def load_seller_monthly(seller_id: str):
    return SellerAnalytics().monthly_sales(seller_id)


def render() -> None:
    set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
    st.title("🏪 Seller Analytics")
    st.caption("Compare seller sales, order volume, buyer ratings, and delivery experience. Sales use item prices and exclude freight.")
    if not db.test_connection():
        st.error("Cannot connect to PostgreSQL. Check the Settings page and database service, then reload.")
        return
    with st.spinner("Summarizing seller orders and reviews…"):
        frame = load_seller_performance()
    if frame.empty:
        st.info("No seller records are available yet.")
        return
    active = frame[frame["items_sold"] > 0]
    total_sales = float(active["gross_sales"].sum())
    total_orders = int(active["orders"].sum())
    total_items = int(active["items_sold"].sum())
    reviewed = active[active["reviewed_orders"] > 0]
    avg_review = float((reviewed["avg_review"] * reviewed["reviewed_orders"]).sum() / reviewed["reviewed_orders"].sum()) if not reviewed.empty else 0.0
    kpis = st.columns(4)
    kpis[0].metric("Sellers in catalog", f"{len(frame):,}")
    kpis[1].metric("Active sellers", f"{len(active):,}")
    kpis[2].metric("Gross item sales", f"R$ {total_sales:,.2f}")
    kpis[3].metric("Average review", f"{avg_review:.2f} / 5")
    st.caption(f"{total_items:,} items across {total_orders:,} seller-order pairs. One order may contain items from multiple sellers.")

    top = active.head(10).copy()
    left, right = st.columns(2)
    with left:
        st.plotly_chart(ChartBuilder.horizontal_bar(top, "seller_id", "gross_sales", "Top 10 Sellers by Item Sales"), width="stretch")
    with right:
        states = active.groupby("state", dropna=False).agg(sellers=("seller_id", "nunique"), gross_sales=("gross_sales", "sum")).reset_index()
        states["state"] = states["state"].fillna("Unknown")
        states = states.sort_values("gross_sales", ascending=False).head(12)
        st.plotly_chart(ChartBuilder.horizontal_bar(states, "state", "gross_sales", "Seller Sales by State"), width="stretch")

    st.subheader("Seller trend")
    chosen = st.selectbox("Choose a seller from the top 10", top["seller_id"].tolist(), format_func=lambda seller: (
        f"{seller} · {active.loc[active.seller_id == seller, 'state'].iloc[0] or 'Unknown'} · "
        f"R$ {active.loc[active.seller_id == seller, 'gross_sales'].iloc[0]:,.0f}"
    ))
    monthly = load_seller_monthly(chosen)
    if not monthly.empty:
        st.plotly_chart(ChartBuilder.line(monthly, "month", "gross_sales", f"Monthly Item Sales · {chosen}", "Sales (R$)"), width="stretch")
    else:
        st.info("This seller has no dated item sales to chart.")

    st.subheader("Seller service signals")
    st.caption("Ratings are averaged per distinct seller/order pair, so multiple items from one seller in an order do not multiply that order’s review. Delivery averages are item-weighted because delivery is recorded at order level.")
    established = active[active["items_sold"] >= 20]
    if not established.empty:
        low = established.nsmallest(10, "avg_review").copy()
        low["seller_id"] = low["seller_id"].str.slice(0, 10)
        st.dataframe(low[["seller_id", "state", "items_sold", "orders", "gross_sales", "avg_review", "reviewed_orders", "avg_delivery_days"]].rename(columns={
            "seller_id": "Seller ID", "state": "State", "items_sold": "Items", "orders": "Orders",
            "gross_sales": "Sales (R$)", "avg_review": "Review / 5", "reviewed_orders": "Reviewed orders",
            "avg_delivery_days": "Avg delivery (days)",
        }), hide_index=True, width="stretch")
        st.caption("Lowest average review scores among sellers with at least 20 items; smaller seller samples are excluded to reduce noise.")
    with st.expander("All seller records"):
        st.dataframe(frame.rename(columns={"seller_id": "Seller ID", "state": "State", "city": "City",
            "items_sold": "Items", "orders": "Orders", "gross_sales": "Sales (R$)",
            "avg_delivery_days": "Avg delivery (days)", "avg_review": "Review / 5",
            "reviewed_orders": "Reviewed orders", "low_review_orders": "Low review orders"}),
            hide_index=True, width="stretch")


render()
