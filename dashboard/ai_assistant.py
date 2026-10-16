"""Conversational business-data assistant (Module 19)."""

import os
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from services.charts import ChartBuilder, set_chart_theme
from services.llm_chat import generate_chat_reply
from services.nl_sql import (
    METRIC_LABELS,
    QueryPlan,
    compile_safe_query,
    create_plan,
    execute_read_only,
)


def _follow_up_question(question: str, history: list[dict]) -> str:
    """Carry a simple year/state refinement into the last successful question."""
    clean = " ".join(question.split())
    followup = clean.casefold()
    if not history or not any(
        word in followup for word in ("what about", "how about", "and in", "instead", "same for")
    ):
        return clean
    previous = next(
        (item.get("question", "") for item in reversed(history) if item.get("plan")),
        "",
    )
    if not previous:
        return clean
    year = re.search(r"\b20\d{2}\b", clean)
    state = re.search(r"\b(?:in|for|from)\s+([A-Za-z]{2})\b", clean)
    if year:
        previous = re.sub(r"\b20\d{2}\b", year.group(0), previous, count=1) if re.search(r"\b20\d{2}\b", previous) else f"{previous} in {year.group(0)}"
    elif state:
        previous = f"{previous} in {state.group(1)}"
    else:
        return clean
    return previous


def _llm_secret(name: str, environment_name: str, default: str = "") -> str:
    """Read optional app secrets or environment values without displaying them."""
    try:
        llm_secrets = st.secrets.get("llm", {})
        value = llm_secrets.get(name, "") if hasattr(llm_secrets, "get") else ""
    except Exception:
        value = ""
    return str(value or os.getenv(environment_name, default)).strip()


def _answer_from_data(plan: QueryPlan, result: pd.DataFrame) -> str:
    label = METRIC_LABELS[plan.metric]
    if result.empty:
        return f"I couldn't find any rows for that question. The measure was **{label}**."
    if "group_value" not in result.columns:
        value = float(result.iloc[0]["value"])
        if plan.metric in {"gross_sales", "average_order_value", "payment_value"}:
            formatted = f"R$ {value:,.2f}"
        elif plan.metric == "average_review":
            formatted = f"{value:.2f} out of 5"
        else:
            formatted = f"{value:,.0f}"
        return f"**{label}: {formatted}.** This result comes from the project database."
    ranked = result.sort_values("value", ascending=False, kind="stable")
    best = ranked.iloc[0]
    if plan.metric in {"gross_sales", "average_order_value", "payment_value"}:
        formatted = f"R$ {float(best['value']):,.2f}"
    elif plan.metric == "average_review":
        formatted = f"{float(best['value']):.2f} out of 5"
    else:
        formatted = f"{float(best['value']):,.0f}"
    dimension_label = plan.dimension.replace("_", " ")
    return f"I found **{len(result):,} {dimension_label} groups**. The highest is **{best['group_value']}** with **{formatted}** ({label}). The chart and full result table are below."


def _run_data_question(question: str, provider: str, api_key: str, model: str, history: list[dict]) -> dict:
    effective_question = _follow_up_question(question, history)
    plan = create_plan(effective_question, provider=provider, api_key=api_key, model=model)
    sql, params = compile_safe_query(plan)
    result = execute_read_only(sql, params)
    answer = _answer_from_data(plan, result)
    if provider != "Built-in parser":
        recent = [
            {"role": item["role"], "content": item["content"]}
            for item in history[-8:]
            if item.get("role") in {"user", "assistant"}
        ]
        preview = result.head(25).to_dict(orient="records")
        answer = generate_chat_reply(
            provider, api_key, model,
            recent + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": f"Verified database result: {preview}. Measure: {METRIC_LABELS[plan.metric]}."},
            ],
            system_prompt=(
                "You are a concise business analytics assistant. Answer only from the verified database result in the conversation. "
                "Do not invent facts or claim you ran SQL. Explain the result plainly and mention when the sample is limited."
            ),
        )
    return {
        "role": "assistant",
        "content": answer,
        "plan": plan.__dict__,
        "question": effective_question,
        "result": result.to_dict(orient="records"),
        "columns": list(result.columns),
    }


def _respond(question: str, provider: str, api_key: str, model: str, history: list[dict]) -> dict:
    try:
        return _run_data_question(question, provider, api_key, model, history)
    except ValueError as exc:
        # Greetings/general help can still use chat; unsupported data questions
        # receive a scope reminder so the assistant doesn't invent metrics.
        if provider != "Built-in parser":
            recent = [
                {"role": item["role"], "content": item["content"]}
                for item in history[-8:]
                if item.get("role") in {"user", "assistant"}
            ]
            try:
                reply = generate_chat_reply(
                    provider, api_key, model, recent + [{"role": "user", "content": question}],
                    system_prompt=(
                        "You are the AI Business Analytics Assistant for the Brazilian Olist e-commerce dataset. "
                        "For greetings and general product help, respond naturally. Never invent dataset findings. "
                        "For unsupported dataset questions, say what you cannot query and suggest supported measures: sales, orders, customers, average order value, reviews, payments; grouped by month, category, state, seller state, status, or payment method where supported."
                    ),
                )
                return {"role": "assistant", "content": reply}
            except Exception as api_error:
                return {"role": "assistant", "content": str(api_error)}
        if any(term in question.casefold() for term in ("hi", "hello", "hey", "help")):
            return {
                "role": "assistant",
                "content": "Hi! Ask me about sales, orders, customers, average order value, reviews, or payments. I can group results by month, category, Brazilian state, seller state, order status, or payment method. For example: **What were monthly sales in 2018?**",
            }
        return {
            "role": "assistant",
            "content": f"I couldn't map that to a supported database question yet. {exc} Try a measure such as sales, orders, customers, average order value, reviews, or payments, and optionally group it by month, category, state, or status.",
        }
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            return {"role": "assistant", "content": f"I couldn't complete that request: {exc}"}
        return {"role": "assistant", "content": "I couldn't complete the database request. Check that PostgreSQL is running and the project database is available, then try again."}


light_theme = st.session_state.get("light_theme", False)
set_chart_theme("light" if light_theme else "dark")
st.title("AI business assistant")
st.caption("Ask follow-up questions about your business data. Database answers run through Module 18's validated, read-only query engine.")

openai_key = _llm_secret("openai_api_key", "OPENAI_API_KEY")
anthropic_key = _llm_secret("anthropic_api_key", "ANTHROPIC_API_KEY")
configured_provider = _llm_secret("provider", "LLM_PROVIDER").casefold()
providers = ["Built-in parser"]
if anthropic_key:
    providers.append("Claude API")
if openai_key:
    providers.append("OpenAI API")
default_provider = {"anthropic": "Claude API", "openai": "OpenAI API"}.get(configured_provider, "Built-in parser")
provider = st.selectbox(
    "Chat engine", providers,
    index=providers.index(default_provider) if default_provider in providers else 0,
    key="ai_chat_provider",
)
if provider == "Claude API":
    api_key = anthropic_key
    model = _llm_secret("anthropic_model", "ANTHROPIC_MODEL", "claude-sonnet-4-6")
elif provider == "OpenAI API":
    api_key = openai_key
    model = _llm_secret("openai_model", "OPENAI_MODEL", "gpt-4.1-mini")
else:
    api_key = model = ""
    st.info("Built-in mode is ready without an API key. Claude/OpenAI API access is optional and may be billed separately.")

st.markdown("Try: *What were monthly sales in 2018?* · *Show top 5 categories by sales* · *How many orders were placed by state?*")
st.session_state.setdefault("ai_chat_messages", [])
toolbar, _ = st.columns([1, 5])
with toolbar:
    if st.button("Clear chat", icon=":material/delete_sweep:", key="clear_ai_chat"):
        st.session_state["ai_chat_messages"] = []
        st.rerun()

for message in st.session_state["ai_chat_messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("result") is not None:
            result = pd.DataFrame(message["result"], columns=message.get("columns"))
            plan = QueryPlan(**message["plan"])
            if "group_value" in result.columns and not result.empty:
                chart_data = result.set_index("group_value")["value"]
                fig = ChartBuilder.bar(
                    chart_data.reset_index(), x="group_value", y="value",
                    title=METRIC_LABELS[plan.metric],
                )
                st.plotly_chart(fig, width="stretch", alt=f"{METRIC_LABELS[plan.metric]} query result")
                result = result.rename(columns={"group_value": plan.dimension.replace("_", " ").title(), "value": METRIC_LABELS[plan.metric]})
            elif "value" in result.columns:
                result = result.rename(columns={"value": METRIC_LABELS[plan.metric]})
            st.dataframe(result, hide_index=True, width="stretch", alt="Verified business data query result")
            with st.expander("Query details"):
                sql, params = compile_safe_query(plan)
                st.code(sql, language="sql")
                if params:
                    st.json(params)
                st.caption("Compiled from approved templates; read-only database transaction with an 8-second statement timeout.")

if prompt := st.chat_input("Ask about your business data", max_chars=500, key="ai_chat_input"):
    history = st.session_state["ai_chat_messages"]
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Checking your question…"):
            reply = _respond(prompt, provider, api_key, model, history[:-1])
        st.markdown(reply["content"])
        if reply.get("result") is not None:
            result = pd.DataFrame(reply["result"], columns=reply.get("columns"))
            plan = QueryPlan(**reply["plan"])
            if "group_value" in result.columns and not result.empty:
                fig = ChartBuilder.bar(result, x="group_value", y="value", title=METRIC_LABELS[plan.metric])
                st.plotly_chart(fig, width="stretch", alt=f"{METRIC_LABELS[plan.metric]} query result")
                result = result.rename(columns={"group_value": plan.dimension.replace("_", " ").title(), "value": METRIC_LABELS[plan.metric]})
            elif "value" in result.columns:
                result = result.rename(columns={"value": METRIC_LABELS[plan.metric]})
            st.dataframe(result, hide_index=True, width="stretch", alt="Verified business data query result")
            with st.expander("Query details"):
                sql, params = compile_safe_query(plan)
                st.code(sql, language="sql")
                if params:
                    st.json(params)
                st.caption("Compiled from approved templates; read-only database transaction with an 8-second statement timeout.")
    history.append(reply)
