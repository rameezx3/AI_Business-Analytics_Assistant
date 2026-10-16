"""Customer and product exploration for an uploaded dataset."""

import streamlit as st

from services.charts import ChartBuilder, set_chart_theme
from services.upload_workspace import (
    customer_dimension,
    find_column,
    product_dimension,
    require_upload,
    sales_groups,
)


set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
upload = require_upload()
profile = upload["profile"]
frame, sales = profile["frame"], profile.get("sales")
st.title("Customers & products")
st.caption(f"Customer and product patterns in **{upload['filename']}**")

customer = customer_dimension(frame)
order = find_column(frame, "order_id", "transaction_id", "invoice_id", "receipt_id")
segment = find_column(frame, "segment", "customer_segment", "customer_type")
product = product_dimension(frame)

if customer:
    customer_orders = frame.groupby(customer, dropna=True)[order].nunique() if order else frame[customer].value_counts(dropna=True)
    distinct_customers = int(customer_orders.size)
    repeat_customers = int((customer_orders > 1).sum()) if order else None
    average_customer_sales = None
    if sales:
        customer_sales = frame.groupby(customer, dropna=True)[sales].sum()
        average_customer_sales = float(customer_sales.mean()) if not customer_sales.empty else 0.0
    metrics = st.columns(3)
    metrics[0].metric("Distinct customers", f"{distinct_customers:,}")
    metrics[1].metric("Repeat customers", f"{repeat_customers:,}" if repeat_customers is not None else "Need order ID")
    metrics[2].metric("Average sales per customer", f"{average_customer_sales:,.2f}" if average_customer_sales is not None else "Need sales column")
    if order and distinct_customers:
        repeat_rate = repeat_customers / distinct_customers * 100
        st.info(f"{repeat_rate:.1f}% of identified customers appear on more than one distinct order in this file.")
    if sales:
        top_customers = frame.groupby(customer, dropna=True)[sales].sum().nlargest(12).sort_values().reset_index()
        st.subheader("Top customers by sales")
        st.plotly_chart(ChartBuilder.horizontal_bar(top_customers, customer, sales, "Top customers by sales"), width="stretch")
else:
    st.info("No customer identifier was detected. Add a customer_id, client_id, or buyer_id column for customer-level insights.")

left, right = st.columns(2)
if product:
    grouped = sales_groups(frame, product, sales)
    value = sales or "Records"
    grouped = grouped.sort_values(value, ascending=False).head(12)
    with left:
        st.subheader("Product / category performance")
        st.plotly_chart(ChartBuilder.horizontal_bar(grouped, product, value, f"Top {product.replace('_', ' ')}"), width="stretch")
else:
    left.info("No product or category column was detected.")

if segment:
    segment_groups = sales_groups(frame, segment, sales).sort_values(sales or "Records", ascending=False)
    with right:
        st.subheader("Customer segments")
        st.plotly_chart(ChartBuilder.bar(segment_groups, segment, sales or "Records", f"{('Sales' if sales else 'Records')} by segment"), width="stretch")
else:
    right.info("Add a segment or customer_type column to compare customer groups.")
