"""Evidence-linked business insight dashboard (Module 20)."""

import sys
import os
import json
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.connection import db
from services.customer_analytics import CustomerAnalytics
from services.customer_segmentation import segment_customers
from services.kpi import KPICalculator
from services.llm_chat import generate_chat_reply
from services.product_analytics import ProductAnalytics
from services.recommendations import RecommendationEngine
from services.sales_analytics import SalesAnalytics
from services.business_insights import generate_business_insights


@st.cache_data(ttl=3600, max_entries=2, show_spinner="Reviewing verified business metrics…")
def load_business_insights() -> tuple[list[dict[str, object]], pd.Timestamp, dict[str, float]]:
    """Load source metrics and generate the same auditable insights per refresh."""
    kpis = KPICalculator().calculate()
    monthly = SalesAnalytics().monthly_sales()
    customers = CustomerAnalytics().customer_table()
    segmented, profiles, cutoff = segment_customers(customers)
    categories = ProductAnalytics().categories()
    regional = RecommendationEngine().regional_delivery()
    insights = generate_business_insights(kpis, monthly, profiles, categories, regional, cutoff)
    stats = {
        "revenue": float(kpis.total_revenue),
        "customers": float(kpis.unique_customers),
        "repeat_rate": float(kpis.repeat_customer_rate_pct),
        "average_order_value": float(kpis.average_order_value),
    }
    return insights, cutoff, stats


st.title("Business insights")
st.caption("A measured view of sales, customers, product experience, and delivery—with evidence and limits shown for every finding.")

if not db.test_connection():
    st.error("Cannot connect to PostgreSQL. Check the service and project `.env`, then reload this page.")
    st.stop()

try:
    insights, cutoff, stats = load_business_insights()
except Exception:
    st.error("Business insights could not be loaded. Check the database connection and confirm the analytics tables are available.")
    st.stop()

metric_cols = st.columns(4)
metric_cols[0].metric("Insights generated", len(insights))
metric_cols[1].metric("Historical item sales", f"R$ {stats['revenue']:,.0f}")
metric_cols[2].metric("Unique customers", f"{stats['customers']:,.0f}")
metric_cols[3].metric("Data cutoff", cutoff.strftime("%d %b %Y"))

st.info(
    "These findings are generated from the project’s historical Olist data. "
    "They describe patterns, not causes or guaranteed financial outcomes. "
    "Validate each finding against current company data before acting."
)

if not insights:
    st.success("No insight rules produced a finding for the current snapshot.")
else:
    def _llm_secret(name: str, environment_name: str, default: str = "") -> str:
        try:
            llm_secrets = st.secrets.get("llm", {})
            value = llm_secrets.get(name, "") if hasattr(llm_secrets, "get") else ""
        except Exception:
            value = ""
        return str(value or os.getenv(environment_name, default)).strip()

    anthropic_key = _llm_secret("anthropic_api_key", "ANTHROPIC_API_KEY")
    openai_key = _llm_secret("openai_api_key", "OPENAI_API_KEY")
    ai_providers = ["Claude API", "OpenAI API"]
    if not anthropic_key:
        ai_providers.remove("Claude API")
    if not openai_key:
        ai_providers.remove("OpenAI API")

    with st.container(border=True):
        st.subheader("Optional AI briefing")
        if not ai_providers:
            st.caption("The evidence-based findings below work locally. Add a Claude or OpenAI API key in `.env` to generate an optional narrative briefing.")
        else:
            selected_provider = st.selectbox("Briefing model", ai_providers, key="business_insights_provider")
            selected_key = anthropic_key if selected_provider == "Claude API" else openai_key
            selected_model = _llm_secret(
                "anthropic_model" if selected_provider == "Claude API" else "openai_model",
                "ANTHROPIC_MODEL" if selected_provider == "Claude API" else "OPENAI_MODEL",
                "claude-sonnet-4-6" if selected_provider == "Claude API" else "gpt-4.1-mini",
            )
            st.caption("This makes one provider API call when clicked. API usage may be billed separately.")
            if st.button("Generate AI briefing", type="primary", icon=":material/auto_awesome:"):
                fact_packet = [
                    {key: item[key] for key in ("id", "area", "title", "summary", "evidence", "action", "limitation")}
                    for item in insights
                ]
                try:
                    st.session_state["business_insights_ai_briefing"] = generate_chat_reply(
                        selected_provider,
                        selected_key,
                        selected_model,
                        [{"role": "user", "content": json.dumps(fact_packet, ensure_ascii=False)}],
                        system_prompt=(
                            "Write a concise executive briefing about the supplied measured findings. Use only facts and numbers from the JSON. "
                            "Do not calculate, add, or estimate values; do not claim causation or guaranteed outcomes. "
                            "Mention that the source is historical Olist data and point readers to the evidence cards for exact values. "
                            "Give at most three short priorities and keep recommendations aligned with the supplied actions."
                        ),
                    )
                except Exception as exc:
                    st.session_state["business_insights_ai_briefing"] = f"The AI briefing could not be generated: {exc}"
            if st.session_state.get("business_insights_ai_briefing"):
                st.markdown(st.session_state["business_insights_ai_briefing"])
                st.caption("AI-written summary · review the evidence cards below for source values and limitations.")

    area_options = ["All areas", *dict.fromkeys(str(item["area"]) for item in insights)]
    selected_area = st.selectbox("Focus area", area_options)
    visible = insights if selected_area == "All areas" else [item for item in insights if item["area"] == selected_area]

    for item in visible:
        with st.container(border=True):
            st.subheader(item["title"])
            st.caption(f"{item['area']} · {item['priority']}")
            st.write(item["summary"])
            if item.get("chart"):
                chart = pd.DataFrame(item["chart"])
                chart = chart.rename(columns={"category": "Category", "gross_sales": "Item sales (R$)"})
                st.bar_chart(chart, x="Category", y="Item sales (R$)", horizontal=True, alt="Gross item sales in the three leading categories")
            st.markdown("**Evidence**")
            for evidence in item["evidence"]:
                st.markdown(f"- {evidence}")
            st.markdown(f"**Suggested next step:** {item['action']}")
            st.caption(f"Limit: {item['limitation']}")

    with st.expander("How these insights are generated"):
        st.markdown(
            "- Sales momentum uses year-over-year comparisons only for months with at least 500 orders.\n"
            "- Customer behavior uses relative RFM groups anchored to the latest purchase date in the dataset.\n"
            "- Category review signals require at least 100 reviewed orders and sales at or above the category 75th percentile.\n"
            "- Delivery exceptions require at least 1,000 orders, at least 2% of item sales, and delivery time more than 15% above the order-weighted baseline.\n"
            "- Values come from the KPI, sales, customer, product, and delivery services. No model invents or changes the measurements; this page works without an API key."
        )

    export_rows = [
        {
            "area": item["area"], "priority": item["priority"], "insight": item["title"],
            "summary": item["summary"], "evidence": " | ".join(item["evidence"]),
            "suggested_action": item["action"], "limitation": item["limitation"],
        }
        for item in visible
    ]
    st.download_button(
        "Download insights as CSV", data=pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig"),
        file_name="business_insights.csv", mime="text/csv", icon=":material/download:",
    )
