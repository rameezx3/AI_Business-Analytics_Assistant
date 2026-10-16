"""Evidence-backed, rule-driven business recommendations (Module 17)."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.connection import db
from services.customer_analytics import CustomerAnalytics
from services.customer_segmentation import segment_customers
from services.product_analytics import ProductAnalytics
from services.recommendations import RecommendationEngine


@st.cache_data(ttl=3600, max_entries=2)
def load_recommendations() -> tuple[list[dict[str, object]], pd.Timestamp]:
    """Load existing analytics once per hour, then apply the transparent rules."""
    people = CustomerAnalytics().customer_table()
    segmented, segment_profile, data_cutoff = segment_customers(people)
    categories = ProductAnalytics().categories()
    regions = RecommendationEngine().regional_delivery()
    findings = RecommendationEngine.generate(
        customer_segments=segment_profile,
        total_customers=len(segmented),
        categories=categories,
        regional=regions,
    )
    return findings, data_cutoff


st.title("💡 Business Recommendations")
st.caption("Practical next steps tied to measured customer, product, and delivery signals.")

if not db.test_connection():
    st.error("Cannot connect to the database. Check PostgreSQL and the project `.env`, then reload this page.")
    st.stop()

try:
    findings, data_cutoff = load_recommendations()
except Exception as exc:
    st.error(f"Recommendations could not be generated: {exc}")
    st.stop()

high_count = sum(item["priority"] == "High" for item in findings)
medium_count = sum(item["priority"] == "Medium" for item in findings)
summary = st.columns(3)
summary[0].metric("Evidence-backed actions", len(findings))
summary[1].metric("High priority", high_count)
summary[2].metric("Data cutoff", data_cutoff.strftime("%d %b %Y"))

st.info(
    "These are transparent, rule-based suggestions from the Olist historical dataset. "
    f"Its latest order is **{data_cutoff:%d %B %Y}**; validate every signal against current company data before acting. "
    "Priority describes the strength of the observed rule, not a predicted financial return."
)

if not findings:
    st.success("No recommendation thresholds were met in the current snapshot.")
else:
    for index, item in enumerate(findings, start=1):
        with st.container(border=True):
            st.subheader(f"{index}. {item['title']}")
            st.caption(f"{item['priority']} priority · {item['area']}")
            st.write(item["signal"])
            st.markdown(f"**Recommended next step:** {item['action']}")
            with st.expander("Evidence, rule, and limitations"):
                st.markdown("**Evidence**")
                for line in item["evidence"]:
                    st.markdown(f"- {line}")
                st.markdown(f"**Trigger rule:** {item['rule']}")
                st.caption(f"Limit: {item['limitation']}")

    export = pd.DataFrame([
        {
            "priority": item["priority"], "area": item["area"], "recommendation": item["title"],
            "evidence": " | ".join(item["evidence"]), "action": item["action"],
            "rule": item["rule"], "limitation": item["limitation"],
            "data_cutoff": data_cutoff.strftime("%Y-%m-%d"),
        }
        for item in findings
    ])
    st.download_button(
        "Download recommendations CSV",
        data=export.to_csv(index=False).encode("utf-8-sig"),
        file_name="business_recommendations.csv",
        mime="text/csv",
    )

with st.expander("How recommendations are produced"):
    st.markdown(
        "- The rules reuse Module 10 customer segments, Module 12 category sales and review summaries, "
        "and an order-level delivery query.\n"
        "- Each suggestion shows the measured signal, its threshold, a practical action, and a limitation.\n"
        "- No generative AI or external model is called in this module; the same data and rules produce the same recommendations.\n"
        "- These associations do not establish causation. Use a small measured pilot and current data before committing budget."
    )
