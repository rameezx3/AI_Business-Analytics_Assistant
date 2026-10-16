"""Natural-language question to validated, read-only SQL dashboard (Module 18)."""

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from services.charts import ChartBuilder, set_chart_theme
from services.nl_sql import (
    METRIC_LABELS,
    QueryPlan,
    compile_safe_query,
    create_plan,
    execute_read_only,
)


def _llm_secret(name: str, environment_name: str, default: str = "") -> str:
    """Read local Streamlit secrets first, then environment/.env without displaying values."""
    try:
        llm_secrets = st.secrets.get("llm", {})
        value = llm_secrets.get(name, "") if hasattr(llm_secrets, "get") else ""
    except Exception:
        value = ""
    return str(value or os.getenv(environment_name, default)).strip()


def _format_value(metric: str, value: object) -> str:
    number = float(value)
    if metric in {"gross_sales", "average_order_value", "payment_value"}:
        return f"R$ {number:,.2f}"
    if metric == "average_review":
        return f"{number:.2f} / 5"
    return f"{number:,.0f}"


light_theme = st.session_state.get("light_theme", False)
set_chart_theme("light" if light_theme else "dark")
st.title("💬 Ask your business data")
st.caption("Ask a supported question in plain English. The app creates a query plan, compiles safe SQL, and returns a chart and result table.")

openai_key = _llm_secret("openai_api_key", "OPENAI_API_KEY")
anthropic_key = _llm_secret("anthropic_api_key", "ANTHROPIC_API_KEY")
providers = ["Built-in parser"]
if anthropic_key:
    providers.append("Claude API")
if openai_key:
    providers.append("OpenAI API")
configured_provider = _llm_secret("provider", "LLM_PROVIDER").casefold()
default_provider = {"anthropic": "Claude API", "openai": "OpenAI API"}.get(configured_provider, "Built-in parser")
provider = st.selectbox("Question interpreter", providers, index=providers.index(default_provider) if default_provider in providers else 0)
if provider == "Claude API":
    api_key = anthropic_key
    model = _llm_secret("anthropic_model", "ANTHROPIC_MODEL", "claude-sonnet-4-6")
elif provider == "OpenAI API":
    api_key = openai_key
    model = _llm_secret("openai_model", "OPENAI_MODEL", "gpt-4.1-mini")
else:
    api_key = ""
    model = ""

if provider == "Built-in parser":
    st.info(
        "Local mode is ready without an API key. It recognizes supported business questions and does not call Claude or OpenAI. "
        "To enable either model, configure its API key locally; provider API usage may be billed separately."
    )
else:
    st.caption(f"Using {provider} · {model}. Only your question is sent to the provider; database rows stay in PostgreSQL.")

with st.expander("Example questions and supported scope"):
    st.markdown(
        "- What were monthly sales in 2018?\n"
        "- Show the top 10 categories by sales\n"
        "- How many orders were placed by state?\n"
        "- Which order statuses have the most orders?\n"
        "- How many customers are in SP?\n"
        "- What is the average review score by category?\n"
        "- Show payment value by payment method\n"
        "- What is the average order value?\n\n"
        "Supported measures: gross item sales, orders with items, orders placed, unique customers, average order value, "
        "average review score, and payment value. Results can be grouped by month, category, buyer state, seller state, "
        "order status, or payment method where the measure supports it. Optional filters: year and two-letter Brazilian state code."
    )

with st.form("natural_language_query_form"):
    question = st.text_area(
        "Your question", value="Show monthly sales in 2018", max_chars=500,
        placeholder="For example: What were the top 10 categories by sales?",
    )
    submitted = st.form_submit_button("Build query and run", type="primary")

if submitted:
    try:
        plan = create_plan(question, provider=provider, api_key=api_key, model=model)
        sql, params = compile_safe_query(plan)
        result = execute_read_only(sql, params)
        st.session_state["nl_sql_last_result"] = {
            "question": question.strip(), "provider": provider, "model": model,
            "plan": plan, "sql": sql, "params": params, "result": result,
        }
    except Exception as exc:
        st.session_state.pop("nl_sql_last_result", None)
        st.error(str(exc))

saved = st.session_state.get("nl_sql_last_result")
if saved:
    plan: QueryPlan = saved["plan"]
    result: pd.DataFrame = saved["result"]
    st.subheader("Answer")
    st.caption(f"Interpreted by {saved['provider']} · Measure: {METRIC_LABELS[plan.metric]}")

    if result.empty:
        st.info("The query ran safely but returned no rows for those filters.")
    elif plan.dimension == "none":
        st.metric(METRIC_LABELS[plan.metric], _format_value(plan.metric, result.iloc[0]["value"]))
    else:
        chart_data = result.copy()
        if plan.dimension == "month":
            chart_data = chart_data.sort_values("group_value")
            fig = ChartBuilder.line(
                chart_data, "group_value", "value", f"{METRIC_LABELS[plan.metric]} by month",
                METRIC_LABELS[plan.metric],
            )
        else:
            chart_data["group_value"] = chart_data["group_value"].astype(str)
            fig = ChartBuilder.horizontal_bar(
                chart_data, "group_value", "value", f"{METRIC_LABELS[plan.metric]} by {plan.dimension.replace('_', ' ')}"
            )
        st.plotly_chart(fig, width="stretch", alt=f"{METRIC_LABELS[plan.metric]} grouped by {plan.dimension.replace('_', ' ')}")

    table = result.copy()
    if "group_value" in table:
        table = table.rename(columns={"group_value": plan.dimension.replace("_", " ").title()})
    table = table.rename(columns={"value": METRIC_LABELS[plan.metric]})
    if not table.empty:
        st.dataframe(table, hide_index=True, width="stretch", alt="Results from the safe business data query")

    with st.expander("See the SQL and parameters"):
        st.code(saved["sql"], language="sql")
        if saved["params"]:
            st.json(saved["params"])
        st.caption("The query is compiled from approved templates, uses bound filter values, runs read-only, and has an 8-second database limit.")

with st.expander("Configure Claude or OpenAI API access (optional)"):
    st.markdown(
        "The local parser works without provider access. Claude.ai or ChatGPT subscription messages do not automatically provide API keys for this app. "
        "If you already have a provider API key, keep it only in this computer's `.env` file or Streamlit secrets; do not paste it into chat or commit it to Git."
    )
    st.code(
        "# Add only the provider you choose to the local .env file\n"
        "LLM_PROVIDER=anthropic\n"
        "ANTHROPIC_API_KEY=your-key\n"
        "ANTHROPIC_MODEL=claude-sonnet-4-6\n\n"
        "# Or use the OpenAI API\n"
        "LLM_PROVIDER=openai\n"
        "OPENAI_API_KEY=your-key\n"
        "OPENAI_MODEL=gpt-4.1-mini",
        language="bash",
    )
