"""Evidence-based summaries for the regular user's uploaded dataset."""

import pandas as pd
import streamlit as st

from services.charts import set_chart_theme
from services.upload_analysis import time_series
from services.upload_workspace import (
    customer_dimension,
    find_column,
    product_dimension,
    require_upload,
    sales_groups,
)


def _insight(title: str, evidence: str, action: str) -> None:
    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.write(evidence)
        st.caption(f"Action to consider: {action}")


set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
upload = require_upload()
profile = upload["profile"]
frame, sales = profile["frame"], profile.get("sales")
st.title("Business insights")
st.caption(f"Evidence-based findings from **{upload['filename']}**. Findings only use fields detected in your file.")

total_cells = profile["rows"] * profile["columns"]
missing_share = profile["missing"] / total_cells * 100 if total_cells else 0.0
if profile["missing"] or profile["duplicates"]:
    _insight(
        "Data quality checks",
        f"{profile['missing']:,} of {total_cells:,} cells are missing ({missing_share:.1f}%), and {profile['duplicates']:,} rows are exact duplicates.",
        "Review the Column profile on Upload Data and resolve important missing values or duplicate records before making decisions.",
    )
else:
    st.success("No missing cells or exact duplicate rows were found in the uploaded file.")

if sales:
    total_sales = float(frame[sales].sum())
    st.metric("Total sales in this file", f"{total_sales:,.2f}", help=f"Calculated as the sum of `{sales}`.")
    dimension = product_dimension(frame)
    if dimension:
        grouped = sales_groups(frame, dimension, sales).sort_values(sales, ascending=False)
        if not grouped.empty:
            winner = grouped.iloc[0]
            share = float(winner[sales]) / total_sales * 100 if total_sales else None
            share_text = f" This is {share:.1f}% of total sales." if share is not None else ""
            _insight(
                f"Leading product grouping: {winner[dimension]}",
                f"It records {float(winner[sales]):,.2f} in `{sales}`.{share_text}",
                "Check availability and compare the next-best groups before shifting inventory or promotion spend.",
            )

    country = find_column(frame, "country", "country_region")
    state = find_column(frame, "state", "state_province", "province")
    geo_dimension = country or state
    if geo_dimension:
        grouped_geo = sales_groups(frame, geo_dimension, sales).sort_values(sales, ascending=False)
        if not grouped_geo.empty:
            winner = grouped_geo.iloc[0]
            _insight(
                f"Highest-sales location: {winner[geo_dimension]}",
                f"This location contributes {float(winner[sales]):,.2f} in `{sales}` across the uploaded records.",
                "Compare this location with the Geography page and check whether the result is supported by enough records.",
            )

    trend = time_series(profile)
    if not trend.empty and sales and len(trend) >= 2:
        first, last = trend.iloc[0], trend.iloc[-1]
        first_value, last_value = float(first[sales]), float(last[sales])
        if first_value != 0:
            change = (last_value - first_value) / abs(first_value) * 100
            direction = "increased" if change >= 0 else "decreased"
            _insight(
                "Latest month compared with the first month",
                f"Monthly sales {direction} by {abs(change):.1f}% from {first['Period']:%b %Y} to {last['Period']:%b %Y}.",
                "Review the full trend on the Sales insights page; two endpoint months do not establish a long-term cause or pattern.",
            )

profit = find_column(frame, "profit", "net_profit", "gross_profit")
if profit and sales and total_sales:
    total_profit = float(pd.to_numeric(frame[profit], errors="coerce").sum())
    margin = total_profit / total_sales * 100
    _insight(
        "Profit margin in the uploaded records",
        f"Summed `{profit}` is {total_profit:,.2f}, equivalent to {margin:.1f}% of summed `{sales}`.",
        "Compare margin by category and location before changing pricing; this simple ratio does not account for unrecorded costs.",
    )

customer, order = customer_dimension(frame), find_column(frame, "order_id", "transaction_id", "invoice_id", "receipt_id")
if customer and order:
    customer_order_counts = frame.groupby(customer, dropna=True)[order].nunique()
    if not customer_order_counts.empty:
        repeat_rate = float((customer_order_counts > 1).mean() * 100)
        _insight(
            "Repeat-customer share",
            f"{repeat_rate:.1f}% of customers with an identifier appear on more than one distinct order in this file.",
            "Use the Customers & products page to inspect customer and segment totals; this describes only the uploaded period.",
        )

order_date = find_column(frame, "order_date", "purchase_date", "created_at")
ship_date = find_column(frame, "ship_date", "shipment_date", "delivery_date", "delivered_date")
if order_date and ship_date:
    dates = pd.DataFrame({
        "order": pd.to_datetime(frame[order_date], errors="coerce"),
        "ship": pd.to_datetime(frame[ship_date], errors="coerce"),
    })
    if order:
        dates["order_id"] = frame[order]
        dates = dates.drop_duplicates("order_id")
    lead_days = (dates["ship"] - dates["order"]).dt.total_seconds() / 86400
    lead_days = lead_days[lead_days.notna() & (lead_days >= 0)]
    if not lead_days.empty:
        timing = "delivery" if "deliver" in ship_date.lower() else "ship"
        _insight(
            f"Average order-to-{timing} time",
            f"The average difference between `{order_date}` and `{ship_date}` is {lead_days.mean():.1f} days for {len(lead_days):,} usable records.",
            "Review the shipping mode and location breakdowns; this measures the dates present in the file, not customer satisfaction.",
        )

if not sales and not any([customer_dimension(frame), product_dimension(frame), find_column(frame, "country", "state", "province", "city")]):
    st.warning("The file has no recognized sales, customer, product, or location fields yet. Check the column profile on Upload Data and use descriptive headers.")

st.caption("These are descriptive findings, not proof that one factor caused another. Missing or incorrectly labeled columns can limit the analysis.")
