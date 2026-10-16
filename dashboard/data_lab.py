"""Upload a CSV/Excel file for private, on-the-fly business analysis."""

import json
from io import BytesIO
from pathlib import Path
import streamlit as st

from services.charts import set_chart_theme
from services.upload_analysis import profile_table, read_table


def render() -> None:
    set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
    st.title("📤 Upload Data")
    st.caption("Upload a sales, customer, or product file to generate an instant exploratory analysis. Files stay in this session and are not written to PostgreSQL.")

    sample_path = Path(__file__).resolve().parent.parent / "data" / "demo_ecommerce_sample.csv"
    with st.container(border=True):
        st.subheader("Try a sample dataset")
        st.write("Download this 600-row synthetic e-commerce file, then select it below. It includes order dates, sales, customers, product categories, order status, and payment method.")
        st.download_button(
            "Download sample CSV",
            data=sample_path.read_bytes(),
            file_name="demo_ecommerce_sample.csv",
            mime="text/csv",
            key="download_demo_ecommerce_sample",
        )
        st.caption("Synthetic data for demonstration, not real customer information.")
        st.markdown("Source and license: [Hugging Face e-commerce orders dataset · MIT](https://huggingface.co/datasets/millat/e-commerce-orders)")
        st.markdown(
            "For international geography, [download the Global Superstore Excel workbook]("
            "https://raw.githubusercontent.com/rishanmenezes/global-superstore-eda-analysis/main/global_superstore_2016.xlsx) "
            "and select its **Orders** worksheet. It includes countries, states/provinces, cities, customers, products, sales, and shipping fields."
        )

    uploaded = st.file_uploader("Choose a CSV or Excel workbook", type=["csv", "xlsx", "xlsm"], max_upload_size=50)
    if uploaded is None:
        saved = st.session_state.get("user_upload")
        if not saved:
            st.info("Start with one row per transaction, order, customer, or product. Clear headers such as order_date, sales, customer_id, and category help the app find useful fields.")
            return
        upload = saved
        profile = upload["profile"]
    else:
        try:
            book = uploaded.getvalue()
            sheets = None
            if uploaded.name.lower().endswith((".xlsx", ".xlsm")):
                import pandas as pd
                sheets = pd.ExcelFile(BytesIO(book), engine="openpyxl").sheet_names
            if sheets:
                preferred_sheet = next((i for i, name in enumerate(sheets) if name.strip().lower() == "orders"), 0)
                sheet = st.selectbox("Worksheet", sheets, index=preferred_sheet)
            else:
                sheet = 0
            data = read_table(uploaded.name, book, sheet)
            profile = profile_table(data)
            upload = {
                "filename": uploaded.name,
                "sheet": sheet if sheets else "CSV",
                "owner_email": st.session_state.get("app_user", {}).get("email"),
                "profile": profile,
            }
            st.session_state["user_upload"] = upload
        except Exception as exc:
            st.error(f"Could not analyze this file: {exc}")
            return

    frame, sales = profile["frame"], profile.get("sales")
    st.caption(f"Current dataset: **{upload['filename']}** · {upload.get('sheet', 'CSV')} · private to this signed-in session")
    metrics = st.columns(4)
    metrics[0].metric("Records", f"{profile['rows']:,}")
    metrics[1].metric("Fields", f"{profile['columns']:,}")
    metrics[2].metric("Total sales", f"{frame[sales].sum():,.2f}" if sales else "Not detected")
    metrics[3].metric("Data quality", f"{profile['missing']:,} missing · {profile['duplicates']:,} duplicate")

    if st.session_state.get("app_user", {}).get("role") == "user":
        st.success("Your dataset is ready. Open an Insights page from the sidebar to explore sales, customers, products, geography, and evidence-based findings.")
        first, second = st.columns(2)
        first.page_link("dashboard/user_sales.py", label="Open sales insights", icon=":material/bar_chart:")
        second.page_link("dashboard/user_insights.py", label="View business insights", icon=":material/query_stats:")

    with st.expander("Column profile", expanded=False):
        st.caption("Detected column types, missing values, unique values, and sample values.")
        details = frame.dtypes.astype(str).rename("type").to_frame()
        details["missing"] = frame.isna().sum()
        details["unique"] = frame.nunique(dropna=True)
        details["sample"] = [json.dumps(frame[c].dropna().head(2).astype(str).tolist(), ensure_ascii=False) for c in frame.columns]
        st.dataframe(details, width="stretch")
    with st.expander("Preview rows", expanded=False):
        st.dataframe(frame.head(100), width="stretch")
    st.download_button("Download analyzed data as CSV", frame.to_csv(index=False).encode("utf-8-sig"), file_name=f"analyzed_{upload['filename'].rsplit('.', 1)[0]}.csv", mime="text/csv")


render()
