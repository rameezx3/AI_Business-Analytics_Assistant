"""Generic, illustrative analytics preview for regular user accounts."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from services.charts import set_chart_theme
from utils.access_control import current_account


def render() -> None:
    account = current_account()
    if not account:
        st.error("Sign in to view the interactive demo.")
        st.stop()

    set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
    st.title("📊 Interactive Demo")
    st.caption("A sample business dashboard. All figures below are illustrative, not connected to company data.")

    monthly = pd.DataFrame({
        "Month": pd.date_range("2025-01-01", periods=12, freq="MS"),
        "Sales": [48200, 51700, 49800, 56300, 59200, 57800, 63400, 66800, 64500, 71200, 75900, 82400],
        "Orders": [420, 451, 438, 486, 512, 498, 544, 572, 553, 601, 638, 691],
        "Customers": [315, 334, 328, 361, 378, 369, 402, 421, 410, 447, 471, 508],
    })
    categories = pd.DataFrame({
        "Category": ["Accessories", "Home", "Office", "Outdoor", "Other"],
        "Sales": [186_500, 143_200, 121_400, 98_700, 197_400],
    })

    kpis = st.columns(3)
    kpis[0].metric("Sample sales", "$747,200", "+12.4%")
    kpis[1].metric("Sample orders", "6,404", "+8.1%")
    kpis[2].metric("Sample customers", "4,744", "+6.7%")

    st.subheader("Sales over time")
    selected_months = st.slider("Months to show", 3, 12, 12, key="demo_month_range")
    recent = monthly.tail(selected_months)
    line = px.line(recent, x="Month", y="Sales", markers=True, title="Illustrative monthly sales")
    line.update_layout(yaxis_title="Sales ($)", xaxis_title=None)
    st.plotly_chart(line, width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("Sample sales by category")
        bar = px.bar(categories.sort_values("Sales"), x="Sales", y="Category", orientation="h")
        bar.update_layout(xaxis_title="Sales ($)", yaxis_title=None)
        st.plotly_chart(bar, width="stretch")
    with right:
        st.subheader("Sample monthly activity")
        st.dataframe(recent[["Month", "Orders", "Customers"]], hide_index=True, width="stretch")

    st.info("Ready to analyze your own business data? Upload a CSV or Excel file. Your upload is analyzed privately for this session.")
    st.page_link("dashboard/data_lab.py", label="Upload a data file", icon="📤", width="content")


render()
