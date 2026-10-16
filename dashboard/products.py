"""Product Analytics page: product/category performance, reviews, and content signals."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.product_analytics import ProductAnalytics


@st.cache_data(ttl=3600)
def load_product_data() -> dict:
    analytics = ProductAnalytics()
    return {
        "summary": analytics.summary(),
        "categories": analytics.categories(),
        "top": analytics.top_products(10),
        "low": analytics.top_products(10, worst=True, min_items=5),
        "content": analytics.content_signals(),
        "reviews": analytics.review_distribution(),
    }


def render() -> None:
    light_theme = st.session_state.get("light_theme", False)
    set_chart_theme("light" if light_theme else "dark")
    st.title("📦 Product Analytics")
    st.caption(
        "Sales are item prices and exclude freight. Product sales are associated with order reviews "
        "at the order level; the same review can inform more than one product in that order."
    )
    if not db.test_connection():
        st.error("Cannot connect to PostgreSQL. Check the Settings page and database service, then reload.")
        return

    data = load_product_data()
    s = data["summary"]
    cols = st.columns(4)
    cols[0].metric("Products in Catalog", f"{s['products']:,}")
    cols[1].metric("Products Sold", f"{s['products_sold']:,}")
    cols[2].metric("Gross Product Sales", f"R$ {s['gross_sales']:,.2f}")
    cols[3].metric("Average Review", f"{s['avg_review']:.2f} / 5", help=f"Across {s['reviews']:,} order reviews")
    st.caption(f"{s['items_sold']:,} item units across {s['orders_with_products']:,} orders and {s['categories']:,} catalog categories.")

    categories = data["categories"]
    st.subheader("Category performance")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            ChartBuilder.horizontal_bar(categories, "category", "gross_sales", "Top Categories by Gross Sales", top_n=10),
            width="stretch",
        )
    with right:
        review_categories = categories[categories["reviewed_orders"] >= 20].nsmallest(10, "avg_review")
        st.plotly_chart(
            ChartBuilder.horizontal_bar(review_categories, "category", "avg_review", "Lowest Category Review Scores (20+ reviewed orders)"),
            width="stretch",
        )
    st.caption("Review scores are averaged over distinct order/category pairs, so multiple same-category items in an order do not multiply its rating.")

    st.subheader("Product leaders and low-volume performers")
    left, right = st.columns(2)
    columns = ["product_id", "category", "items_sold", "orders", "gross_sales", "avg_review"]
    with left:
        st.markdown("**Top 10 by gross sales**")
        st.dataframe(data["top"][columns].rename(columns={
            "product_id": "Product ID", "category": "Category", "items_sold": "Items",
            "orders": "Orders", "gross_sales": "Sales (R$)", "avg_review": "Review / 5",
        }), hide_index=True, width="stretch")
    with right:
        st.markdown("**Lowest sales among products with 5+ items**")
        st.dataframe(data["low"][columns].rename(columns={
            "product_id": "Product ID", "category": "Category", "items_sold": "Items",
            "orders": "Orders", "gross_sales": "Sales (R$)", "avg_review": "Review / 5",
        }), hide_index=True, width="stretch")
        st.caption("The 5-item floor reduces noise from products with only one or two sales.")

    st.subheader("Review quality")
    st.plotly_chart(ChartBuilder.bar(data["reviews"], "review_score", "reviews", "Order Reviews by Score"), width="stretch")

    st.subheader("Product content signals")
    st.caption("Average units sold per listed product by photo-count and description-length bands. This is descriptive, not evidence that content caused sales.")
    content = data["content"]
    if not content.empty:
        content["band"] = content["photo_band"] + " · " + content["description_band"]
        st.plotly_chart(
            ChartBuilder.horizontal_bar(content, "band", "avg_items_per_product", "Average Items Sold per Product", top_n=15),
            width="stretch",
        )
        with st.expander("Content band detail"):
            st.dataframe(content.rename(columns={
                "photo_band": "Photo count", "description_band": "Description length",
                "products": "Products", "items_sold": "Items sold",
                "avg_items_per_product": "Avg items / product", "avg_sales_per_product": "Avg sales / product (R$)",
            }), hide_index=True, width="stretch")

    with st.expander("All category detail"):
        st.dataframe(categories.rename(columns={
            "category": "Category", "items_sold": "Items sold", "products": "Products",
            "orders": "Orders", "gross_sales": "Gross sales (R$)", "avg_item_price": "Avg item price (R$)",
            "avg_review": "Avg review / 5", "reviewed_orders": "Reviewed orders",
            "low_review_orders": "Low scores (1–2)", "positive_review_orders": "High scores (4–5)",
        }), hide_index=True, width="stretch")


render()
