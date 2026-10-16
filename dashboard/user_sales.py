"""Sales trends for the regular user's current upload."""

import streamlit as st

from services.charts import ChartBuilder, set_chart_theme
from services.upload_analysis import time_series
from services.upload_workspace import find_column, measure_name, product_dimension, require_upload, sales_groups


set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
upload = require_upload()
profile = upload["profile"]
frame, sales = profile["frame"], profile.get("sales")
st.title("Sales insights")
st.caption(f"Based on **{upload['filename']}** · session-only analysis")

order_col = find_column(frame, "order_id", "transaction_id", "invoice_id", "receipt_id")
order_count = frame[order_col].nunique(dropna=True) if order_col else len(frame)
metrics = st.columns(4)
metrics[0].metric("Total sales" if sales else "Records", f"{frame[sales].sum():,.2f}" if sales else f"{len(frame):,}")
metrics[1].metric("Average sale" if sales else "Unique rows", f"{frame[sales].mean():,.2f}" if sales else f"{frame.drop_duplicates().shape[0]:,}")
metrics[2].metric("Distinct orders" if order_col else "Records (order proxy)", f"{order_count:,}")
metrics[3].metric("Sales column", sales or "Not detected")

trend = time_series(profile)
if not trend.empty:
    st.subheader("Monthly trend")
    measure = measure_name(sales)
    st.plotly_chart(ChartBuilder.line(trend, "Period", measure, f"Monthly {'sales' if sales else 'record'} trend"), width="stretch")
else:
    st.info("Add a recognizable date column (such as order_date) to see a monthly trend.")

dimension = product_dimension(frame)
profit = find_column(frame, "profit", "net_profit", "gross_profit")
if dimension:
    left, right = st.columns(2)
    grouped = sales_groups(frame, dimension, sales)
    value = measure_name(sales)
    grouped = grouped.sort_values(value, ascending=False).head(12)
    with left:
        st.subheader(f"Top {dimension.replace('_', ' ')}")
        st.plotly_chart(ChartBuilder.horizontal_bar(grouped, dimension, value, f"Top {dimension.replace('_', ' ')} by {value.lower()}"), width="stretch")
    if profit:
        profit_groups = frame.groupby(dimension, dropna=False)[profit].sum().reset_index()
        profit_groups = profit_groups.sort_values(profit, ascending=False).head(12)
        with right:
            st.subheader("Profit by category")
            st.plotly_chart(ChartBuilder.horizontal_bar(profit_groups, dimension, profit, f"Profit by {dimension.replace('_', ' ')}"), width="stretch")

if sales:
    st.caption("Sales totals are calculated by summing the detected sales column. Confirm whether your source records are order-level or item-level before interpreting order averages.")
