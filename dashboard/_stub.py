"""
dashboard/_stub.py

WHY THIS FILE EXISTS:
    Module 7 wires up navigation for ALL 10 dashboard pages named in the
    original spec, but only Home (and partly Settings) have real content
    yet - the rest (Sales, Customers, Products, Orders, Geography,
    Forecast, AI Assistant, Reports) are built in later modules (8-21).
    This gives every unbuilt page a clear, honest placeholder instead of
    a blank screen or a crash, so the navigation itself is fully
    demonstrable right now.
"""

import streamlit as st


def render_stub(page_title: str, icon: str, coming_in: str, will_show: list[str]) -> None:
    """Renders a consistent 'not built yet' placeholder for a future page."""
    st.title(f"{icon} {page_title}")
    st.info(f"This page will be built in **{coming_in}**.")
    st.markdown("**Once built, this page will show:**")
    for item in will_show:
        st.markdown(f"- {item}")
