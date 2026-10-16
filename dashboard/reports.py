"""Downloadable PDF report builder and Module 6 EDA report viewer."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from config import Config
from database.connection import db
from services.business_insights import generate_business_insights
from services.customer_analytics import CustomerAnalytics
from services.customer_segmentation import segment_customers
from services.kpi import KPICalculator
from services.pdf_reports import build_pdf_report
from services.product_analytics import ProductAnalytics
from services.recommendations import RecommendationEngine
from services.sales_analytics import SalesAnalytics
from utils.logger import get_logger

logger = get_logger(__name__)


@st.cache_data(ttl=3600, max_entries=2, show_spinner="Preparing report data from PostgreSQL…")
def load_report_data() -> tuple[list[dict[str, object]], pd.Timestamp, dict[str, float], pd.DataFrame, pd.DataFrame]:
    kpis = KPICalculator().calculate()
    monthly = SalesAnalytics().monthly_sales()
    customers = CustomerAnalytics().customer_table()
    _, profiles, cutoff = segment_customers(customers)
    categories = ProductAnalytics().categories()
    regional = RecommendationEngine().regional_delivery()
    insights = generate_business_insights(kpis, monthly, profiles, categories, regional, cutoff)
    stats = {
        "revenue": float(kpis.total_revenue),
        "customers": float(kpis.unique_customers),
        "repeat_rate": float(kpis.repeat_customer_rate_pct),
        "average_order_value": float(kpis.average_order_value),
    }
    return insights, cutoff, stats, monthly, categories


st.title("Reports")
st.caption("Generate a shareable PDF from verified analytics, or review the saved Module 6 EDA report and figures.")

if not db.test_connection():
    st.error("Cannot connect to PostgreSQL. Check the service and project `.env`, then reload this page.")
    st.stop()

try:
    insights, cutoff, stats, monthly, categories = load_report_data()
except Exception:
    st.error("Report data could not be loaded. Check the database connection and analytics tables, then reload.")
    st.stop()

with st.container(border=True):
    st.subheader("Create a PDF report")
    template = st.selectbox(
        "Report template",
        ["Executive overview", "Sales and product", "Customers and fulfillment"],
        help="Choose which evidence findings and charts appear in the report.",
    )
    st.caption(f"Source: Olist PostgreSQL dataset · data cutoff {cutoff:%d %b %Y} · generated using the latest cached metrics.")
    if st.button("Generate PDF", type="primary", icon=":material/picture_as_pdf:"):
        if template == "Sales and product":
            included_areas = {"Sales performance", "Product mix", "Product experience"}
            selected_insights = [item for item in insights if item["area"] in included_areas]
        elif template == "Customers and fulfillment":
            included_areas = {"Customer behavior", "Fulfillment"}
            selected_insights = [item for item in insights if item["area"] in included_areas]
        else:
            selected_insights = insights
        try:
            pdf_bytes = build_pdf_report(selected_insights, monthly, categories, stats, cutoff, template)
            st.session_state["generated_pdf_report"] = {
                "template": template,
                "data": pdf_bytes,
                "filename": f"business_report_{template.lower().replace(' ', '_')}_{pd.Timestamp.now():%Y%m%d}.pdf",
            }
        except Exception as exc:
            logger.exception("PDF report generation failed")
            st.error(f"PDF generation failed ({type(exc).__name__}). Check the Streamlit terminal for details.")

    generated = st.session_state.get("generated_pdf_report")
    if generated and generated["template"] == template:
        st.download_button(
            "Download PDF report",
            data=generated["data"],
            file_name=generated["filename"],
            mime="application/pdf",
            icon=":material/download:",
            type="primary",
        )
        st.caption(f"PDF ready · {len(generated['data']) / 1024:.0f} KB · includes {len(insights)} evidence-linked findings." if template == "Executive overview" else "PDF ready · includes the selected report template and its evidence-linked findings.")

st.divider()
st.subheader("Exploratory data analysis report")
root = Path(__file__).resolve().parent.parent
eda_path = root / "reports" / "generated" / "eda_report.md"
if eda_path.exists():
    eda_text = eda_path.read_text(encoding="utf-8")
    with st.expander("Read the Module 6 EDA report", expanded=True):
        st.markdown(eda_text)
    st.download_button(
        "Download EDA report (Markdown)", data=eda_text.encode("utf-8"),
        file_name="eda_report.md", mime="text/markdown", icon=":material/download:",
    )
    chart_dir = Config().app.charts_dir
    chart_paths = sorted(chart_dir.glob("*.png"))
    if not chart_paths:
        # Vercel functions can only write to /tmp; keep the committed EDA figures readable.
        chart_dir = root / "charts" / "generated"
        chart_paths = sorted(chart_dir.glob("*.png"))
    if chart_paths:
        with st.expander(f"View the {len(chart_paths)} EDA charts"):
            for start in range(0, len(chart_paths), 3):
                columns = st.columns(3)
                for column, path in zip(columns, chart_paths[start:start + 3]):
                    column.image(str(path), caption=path.stem.replace("_", " ").title(), alt=path.stem.replace("_", " "))
else:
    st.info("No saved EDA report is available yet. Generate it with `python services/eda.py`.")
