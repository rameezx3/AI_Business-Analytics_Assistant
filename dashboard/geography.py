"""Module 13: geographic sales, delivery, and seller-buyer analysis."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px

from database.connection import db
from services.charts import set_chart_theme
from services.geography_analytics import GeographyAnalytics

st.title("🗺️ Geographical Analytics")
st.caption("Compare buyer-state sales and fulfillment, then see how far products travel between sellers and customers.")
set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
if not db.test_connection():
    st.error("Cannot connect to PostgreSQL. Check the Settings page and database service, then reload.")
else:
    with st.spinner("Aggregating regional orders and location data…"):
        analytics = GeographyAnalytics()
        states = analytics.state_performance()
        distance = analytics.distance_summary()
    kpis = st.columns(4)
    kpis[0].metric("Buyer states", f"{len(states):,}")
    kpis[1].metric("Orders", f"{int(states['orders'].sum()):,}")
    kpis[2].metric("Avg seller → buyer", f"{distance['avg_distance_km']:,.0f} km", help=f"Based on {distance['items_with_locations']:,} items with both ZIP centroids.")
    kpis[3].metric("Cross-state items", f"{distance['cross_state_pct']:.1f}%")
    st.subheader("Sales and fulfillment by buyer state")
    left, right = st.columns(2)
    with left:
        mapped = states.dropna(subset=["lat", "lng"])
        map_fig = px.scatter_geo(mapped, lat="lat", lon="lng", size="gross_sales", color="gross_sales",
            hover_name="state", scope="south america", title="Gross sales by Brazilian buyer state",
            color_continuous_scale="Tealgrn", hover_data={"orders": ":,", "gross_sales": ":,.0f"})
        map_fig.update_layout(template="plotly_white" if st.session_state.get("light_theme", False) else "plotly_dark",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(map_fig, width="stretch")
        st.caption("Markers show average customer ZIP-prefix coordinates for each state; they are not official state boundaries.")
    with right:
        delivery = states.dropna(subset=["avg_delivery_days"]).sort_values("avg_delivery_days", ascending=False)
        fig = px.bar(delivery, x="state", y="avg_delivery_days", color="avg_delivery_days",
                     title="Average delivery time by buyer state", labels={"state": "State", "avg_delivery_days": "Days"},
                     color_continuous_scale="Tealgrn")
        fig.update_layout(template="plotly_white" if st.session_state.get("light_theme", False) else "plotly_dark",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
    st.subheader("Regional sales table")
    st.dataframe(states.rename(columns={"state": "Buyer State", "orders": "Orders", "gross_sales": "Gross Sales", "avg_delivery_days": "Avg Delivery (days)"}), hide_index=True, width="stretch")
    st.info(f"Distance uses great-circle distance between average ZIP-prefix coordinates. Median distance: {distance['median_distance_km']:,.0f} km. It is a geographic estimate, not road or courier route distance.")
