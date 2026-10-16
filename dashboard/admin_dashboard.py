"""Read-only operational dashboard for administrators (Module 22)."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import inspect, text

from config import config
from database.connection import db
from utils.access_control import has_admin_access, is_logged_in


DATA_TABLES = (
    "orders", "order_items", "order_payments", "order_reviews", "customers",
    "products", "sellers", "geolocation", "category_translation",
)


@st.cache_data(ttl=120, show_spinner=False)
def _load_snapshot() -> dict:
    """Load a short-lived, read-only snapshot from the configured database."""
    engine = db.engine
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        preparer = engine.dialect.identifier_preparer
        counts = []
        for table in DATA_TABLES:
            if table in tables:
                safe_table = preparer.quote(table)
                count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {safe_table}")
                ).scalar_one()
                counts.append({"Table": table, "Rows": int(count)})

        validation_runs = pd.DataFrame()
        if "validation_log" in tables:
            validation_runs = pd.read_sql_query(text("""
                SELECT run_id, MAX(checked_at) AS checked_at,
                       COUNT(*) AS total_checks,
                       SUM(CASE WHEN UPPER(status) = 'PASS' THEN 1 ELSE 0 END) AS passed,
                       SUM(CASE WHEN UPPER(status) = 'WARN' THEN 1 ELSE 0 END) AS warnings,
                       SUM(CASE WHEN UPPER(status) = 'FAIL' THEN 1 ELSE 0 END) AS failed
                FROM validation_log
                GROUP BY run_id
                ORDER BY MAX(checked_at) DESC
                LIMIT 8
            """), connection)

        quality_summary = pd.DataFrame()
        quality_history = pd.DataFrame()
        if "data_quality_log" in tables:
            quality_summary = pd.read_sql_query(text("""
                SELECT table_name, issue_type, COUNT(*) AS issue_count,
                       MAX(detected_at) AS latest_detected
                FROM data_quality_log
                GROUP BY table_name, issue_type
                ORDER BY issue_count DESC, table_name, issue_type
            """), connection)
            quality_history = pd.read_sql_query(text("""
                SELECT table_name, issue_type, record_identifier,
                       description, action_taken, detected_at
                FROM data_quality_log
                ORDER BY detected_at DESC
                LIMIT 25
            """), connection)

        date_range = None
        if "orders" in tables:
            row = connection.execute(text("""
                SELECT MIN(order_purchase_timestamp), MAX(order_purchase_timestamp)
                FROM orders
            """)).one()
            date_range = row

    return {
        "tables": sorted(tables),
        "counts": pd.DataFrame(counts, columns=["Table", "Rows"]),
        "validation_runs": validation_runs,
        "quality_summary": quality_summary,
        "quality_history": quality_history,
        "date_range": date_range,
    }


def render() -> None:
    st.title("System Health")
    st.caption("Operational health and data-quality monitoring · read-only")

    if not is_logged_in():
        st.error("Sign in to view system health.")
        st.stop()

    if st.button("Refresh system snapshot", type="primary"):
        _load_snapshot.clear()
        st.rerun()

    try:
        snapshot = _load_snapshot()
    except Exception as exc:
        st.error("The system snapshot could not be loaded. Check the database connection and schema.")
        st.caption(f"Diagnostic: {type(exc).__name__}")
        return

    tables = set(snapshot["tables"])
    counts = snapshot["counts"]
    total_rows = int(counts["Rows"].sum()) if not counts.empty else 0
    latest_validation = snapshot["validation_runs"]
    validation = latest_validation.iloc[0] if not latest_validation.empty else None
    latest_quality = snapshot["quality_summary"]
    quality_records = int(latest_quality["issue_count"].sum()) if not latest_quality.empty else 0
    order_range = snapshot["date_range"]

    with st.container(horizontal=True):
        st.metric("Database", "Connected", border=True)
        st.metric("Business tables", f"{len(set(DATA_TABLES) & tables)} / {len(DATA_TABLES)}", border=True)
        st.metric("Rows across source tables", f"{total_rows:,}", border=True)
        st.metric("Cleaning audit records", f"{quality_records:,}", border=True)

    if validation is not None:
        st.subheader("Latest validation run")
        a, b, c, d = st.columns(4)
        a.metric("Checks", int(validation["total_checks"]))
        b.metric("Passed", int(validation["passed"] or 0))
        c.metric("Warnings", int(validation["warnings"] or 0))
        d.metric("Failed", int(validation["failed"] or 0))
        st.caption(f"Run {validation['run_id']} · {validation['checked_at']}")
    else:
        st.info("No validation runs are recorded yet. Run the data validation module to populate this view.")

    if order_range and (order_range[0] or order_range[1]):
        st.caption(f"Order data coverage: {order_range[0]} to {order_range[1]} · dataset timestamps")

    left, right = st.columns(2)
    with left:
        st.subheader("Source table inventory")
        if counts.empty:
            st.warning("No expected business tables were found in the database.")
        else:
            st.dataframe(counts, hide_index=True, alt="Row counts for each business data table")
    with right:
        st.subheader("Recent validation runs")
        if latest_validation.empty:
            st.info("Validation history is not available.")
        else:
            st.dataframe(latest_validation, hide_index=True, alt="Recent data validation run summaries")

    st.subheader("Data-quality findings")
    if latest_quality.empty:
        st.success("No cleaning findings are recorded, or the cleaning log table is not available.")
    else:
        st.dataframe(latest_quality, hide_index=True, alt="Data-quality findings grouped by table and issue")
        with st.expander("View recent cleaning audit records"):
            st.dataframe(snapshot["quality_history"], hide_index=True, alt="Recent audited data cleaning actions")

    if has_admin_access():
        st.subheader("Application configuration")
        st.write(f"**Environment:** {config.app.environment}")
        st.write(f"**Database:** {config.database.name} on {config.database.host}:{config.database.port}")
        st.caption("This dashboard only reads status and audit data. It does not modify records or credentials.")


render()
