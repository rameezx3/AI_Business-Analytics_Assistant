"""Helpers for user-facing insight pages powered by an uploaded file."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st


def current_upload() -> dict | None:
    """Return the active in-memory upload for this browser session, if any."""
    upload = st.session_state.get("user_upload")
    if isinstance(upload, dict) and isinstance(upload.get("profile"), dict):
        return upload
    return None


def find_column(frame: pd.DataFrame, *aliases: str) -> str | None:
    """Match common column names after ignoring spaces and punctuation."""
    normalized = {
        re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_"): column
        for column in frame.columns
    }
    for alias in aliases:
        match = normalized.get(re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_"))
        if match is not None:
            return match
    return None


def product_dimension(frame: pd.DataFrame) -> str | None:
    """Prefer useful product groupings over row-level product identifiers."""
    return find_column(
        frame,
        "category", "product_category", "sub_category", "subcategory",
        "product_name", "product", "item", "sku",
    )


def customer_dimension(frame: pd.DataFrame) -> str | None:
    """Prefer stable customer IDs over display names."""
    return find_column(frame, "customer_id", "client_id", "buyer_id", "customer", "client", "buyer")


def sales_dimension(profile: dict) -> str | None:
    return profile.get("sales")


def require_upload() -> dict:
    """Render a clear next step and stop an insight page when no file is loaded."""
    upload = current_upload()
    if upload is None:
        st.info("Upload a CSV or Excel workbook first. Your file powers these insight pages for this session.")
        st.page_link("dashboard/data_lab.py", label="Open Data Lab", icon=":material/upload_file:")
        st.stop()
    return upload


def sales_groups(frame: pd.DataFrame, dimension: str, sales: str | None) -> pd.DataFrame:
    """Aggregate a grouping column by sales, or by row count when sales is absent."""
    if sales:
        return frame.groupby(dimension, dropna=False)[sales].sum().reset_index()
    return frame[dimension].value_counts(dropna=False).rename_axis(dimension).reset_index(name="Records")


def measure_name(sales: str | None) -> str:
    return sales or "Records"
