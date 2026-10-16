"""Customer segmentation dashboard (Module 16)."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.customer_analytics import CustomerAnalytics
from services.customer_segmentation import SEGMENT_GUIDANCE, segment_customers


@st.cache_data(ttl=3600, max_entries=2)
def load_customer_segments() -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Build and cache a segment snapshot for the customer population."""
    return segment_customers(CustomerAnalytics().customer_table())


light_theme = st.session_state.get("light_theme", False)
set_chart_theme("light" if light_theme else "dark")
st.title("🧭 Customer Segmentation")
st.caption("Understand customer groups by how recently they ordered, how often, and how much they spent.")

if not db.test_connection():
    st.error("Cannot connect to the database. Check PostgreSQL and the project `.env`, then reload this page.")
    st.stop()

try:
    customers, profiles, cutoff = load_customer_segments()
except Exception as exc:
    st.error(f"Customer segments could not be calculated: {exc}")
    st.stop()

present = profiles.loc[profiles["customers"] > 0].copy()
paying_count = int((customers["monetary"] > 0).sum())

kpis = st.columns(4)
kpis[0].metric("People segmented", f"{len(customers):,}")
kpis[1].metric("Paying customers", f"{paying_count:,}")
kpis[2].metric("Segments with customers", f"{len(present):,}")
kpis[3].metric("Data cutoff", cutoff.strftime("%b %Y"))

st.info(
    f"RFM scores use order recency relative to **{cutoff:%d %b %Y}**, order count, and item-price spend. "
    "Spend excludes freight. Scores are relative quintiles within this dataset; segment names come from "
    "explicit rules, so they describe observed behavior rather than predict future purchases."
)

left, right = st.columns(2)
with left:
    fig = ChartBuilder.horizontal_bar(present, "segment", "customers", "Customers in Each Segment")
    st.plotly_chart(fig, width="stretch", alt="Customer count by rule-based RFM segment")
with right:
    fig = ChartBuilder.horizontal_bar(present, "segment", "revenue_share_pct", "Share of Item Sales by Segment")
    st.plotly_chart(fig, width="stretch", alt="Share of item-price sales contributed by each segment")

st.subheader("Segment profiles")
display = present[[
    "segment", "customers", "customer_share_pct", "avg_recency_days", "avg_orders",
    "avg_spend", "median_spend", "revenue_share_pct",
]].rename(columns={
    "segment": "Segment", "customers": "Customers", "customer_share_pct": "Customer share (%)",
    "avg_recency_days": "Avg recency (days)", "avg_orders": "Avg orders",
    "avg_spend": "Avg item spend (R$)", "median_spend": "Median item spend (R$)",
    "revenue_share_pct": "Sales share (%)",
})
st.dataframe(
    display.style.format({
        "Customer share (%)": "{:.2f}%", "Avg recency (days)": "{:,.1f}",
        "Avg orders": "{:.2f}", "Avg item spend (R$)": "R$ {:,.2f}",
        "Median item spend (R$)": "R$ {:,.2f}", "Sales share (%)": "{:.2f}%",
    }), hide_index=True, width="stretch", alt="Customer counts and RFM behavior summary by segment",
)

st.subheader("Explore a segment")
selected = st.selectbox("Choose a segment", present["segment"].tolist())
st.write(SEGMENT_GUIDANCE[selected])
segment_people = customers.loc[customers["segment"] == selected]
states = (segment_people.groupby("state", dropna=False)
          .agg(customers=("customer_unique_id", "size"), item_sales=("monetary", "sum"))
          .reset_index().sort_values("customers", ascending=False).head(10))
state_display = states.rename(columns={"state": "State", "customers": "Customers", "item_sales": "Item sales (R$)"})
state_display["Item sales (R$)"] = state_display["Item sales (R$)"].map(lambda value: f"R$ {value:,.2f}")
st.dataframe(state_display, hide_index=True, width="stretch", alt=f"Top states for customers in {selected}")

st.download_button(
    "Download segment profile CSV",
    data=present.to_csv(index=False).encode("utf-8-sig"),
    file_name="customer_segment_profiles.csv",
    mime="text/csv",
)

with st.expander("How the RFM rules work"):
    st.markdown(
        "- **Recency:** days since each person's last recorded order, measured against the dataset's latest order date.\n"
        "- **Frequency:** number of orders in the customer analytics snapshot.\n"
        "- **Monetary:** lifetime sum of item prices, excluding freight. People with no item-price spend are kept in a separate group.\n"
        "- Paying customers receive relative 1–5 quintile scores for each feature. Recent orders receive a higher recency score.\n"
        "- Explicit rules map those scores to Champions, Loyal, Potential loyalists, New, At risk, Hibernating, or Needs nurturing.\n"
        "- These are descriptive historical groups, not machine-learning clusters and not evidence that an individual will buy again."
    )
